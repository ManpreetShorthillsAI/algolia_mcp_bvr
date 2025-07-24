"""
Streamlit UI for Algolia MCP – FINAL FIXED VERSION
• Correctly parses getApplications result
• Injects applicationName into every downstream tool call
• Works with Node.js MCP server (src/app.ts)
• Includes AI Chat Assistant functionality
"""
 
import os, json, asyncio, threading, time, atexit
from contextlib import AsyncExitStack
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime
 
import streamlit as st
import nest_asyncio
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from algolia_uploader import algolia_upload_app  # type: ignore

# Apply nest_asyncio patch for Streamlit compatibility
nest_asyncio.apply()

# Try to import OpenAI for chat functionality (optional)
try:
    from openai import AzureOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    st.warning("⚠️ OpenAI not installed. Chat functionality will be limited.")

# ──────────────────────────────────
# Chat Message Classes (from algolia_query.py)
# ──────────────────────────────────
@dataclass
class ToolCall:
    name: str
    arguments: Dict[str, Any]
    result: Dict[str, Any]
    success: bool
    timestamp: str

@dataclass
class ChatMessage:
    role: str  # 'user', 'assistant', 'tool'
    content: str
    timestamp: str
    tool_calls: List[ToolCall] = None

# ──────────────────────────────────
# OpenAI Schema Conversion Functions
# ──────────────────────────────────
def _simplify_schema_prop(pn: str, pd: Any) -> dict:
    if not isinstance(pd, dict):
        return {"type": "string", "description": f"Parameter {pn}"}
    ptype = pd.get("type", "string")
    if isinstance(ptype, list):       # pick first
        ptype = ptype[0] if ptype else "string"
 
    out = {"type": ptype,
           "description": pd.get("description", f"Parameter {pn}")}
 
    if ptype == "array":
        items = pd.get("items", {})
        items_type = items.get("type", "string") if isinstance(items, dict) else "string"
        out["items"] = {"type": items_type}
    elif ptype == "object":
        out["additionalProperties"] = True
        if isinstance(pd.get("properties"), dict):
            out["properties"] = {k: _simplify_schema_prop(k, v)
                                 for k, v in pd["properties"].items()}
 
    for k in ("minimum", "maximum", "minLength", "maxLength",
              "pattern", "enum", "example"):
        if k in pd:
            out[k] = pd[k]
    return out
 
def to_openai_schema(tool) -> dict:
    raw = getattr(tool, "inputSchema", {}) or {}
    oa = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
    if isinstance(raw.get("properties"), dict):
        oa["properties"] = {k: _simplify_schema_prop(k, v)
                            for k, v in raw["properties"].items()}
    if isinstance(raw.get("required"), list):
        oa["required"] = raw["required"]
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": getattr(tool, "description",
                                   f"Algolia tool: {tool.name}"),
            "parameters": oa,
        },
    }

# ──────────────────────────────────
# Argument Validation Classes
# ──────────────────────────────────
@dataclass
class ValidationResult:
    success: bool
    arguments: Dict[str, Any]
    missing_fields: List[str]
    warnings: List[str]
    errors: List[str]
 
class ArgPreparer:
    def __init__(self, app_id: str):
        self.GLOBAL_DEFAULTS = {
            "applicationId": app_id,
            "indexName":     "default_index",
            "requestBody":   {},
        }
 
    def prepare(self,
                schema: Dict[str, Any],
                supplied: Dict[str, Any],
                tool_name: str) -> ValidationResult:
        res = ValidationResult(True, dict(supplied), [], [], [])
        if not isinstance(schema, dict):
            res.errors.append("tool schema not dict"); res.success = False
            return res
 
        props = schema.get("properties", {})
        required = schema.get("required", [])
 
        for fld in required:
            if fld not in res.arguments or res.arguments[fld] in ("", None, [], {}):
                val = self._default_for(fld, props.get(fld, {}), tool_name)
                if val is not None:
                    res.arguments[fld] = val
                    res.warnings.append(f"auto-filled '{fld}'")
                else:
                    res.missing_fields.append(fld)
                    res.success = False
 
        # simple type check
        for n, v in res.arguments.items():
            if n in props and not self._type_ok(v, props[n].get("type", "string")):
                res.errors.append(f"'{n}' wrong type")
                res.success = False
        return res
 
    @staticmethod
    def _type_ok(val, etype):
        return ((etype == "string"  and isinstance(val, str)) or
                (etype == "integer" and isinstance(val, int) and not isinstance(val, bool)) or
                (etype == "number"  and isinstance(val, (int, float)) and not isinstance(val, bool)) or
                (etype == "boolean" and isinstance(val, bool)) or
                (etype == "array"   and isinstance(val, list)) or
                (etype == "object"  and isinstance(val, dict)) or
                etype not in ("string","integer","number","boolean","array","object"))
 
    def _default_for(self, fld, fld_schema, tool_name):
        if fld in self.GLOBAL_DEFAULTS:
            return self.GLOBAL_DEFAULTS[fld]
        tl = tool_name.lower()
        if "search" in tl and fld == "searchParams":
            return {"query": ""}
        if "save" in tl and fld == "requestBody":
            return {"data": "sample"}
        if "delete" in tl and fld in ("objectID", "requestBody"):
            return "sample_id" if fld == "objectID" else ["sample_id"]
        typ = fld_schema.get("type", "string")
        return {"string": f"sample_{fld}", "integer": 0, "number": 0.0,
                "boolean": False, "array": [], "object": {}}.get(typ)

# ──────────────────────────────────
# Serialization helpers
# ──────────────────────────────────
def make_serialisable(obj):
    if hasattr(obj, "text"):        # Algolia TextContent
        return obj.text
    if hasattr(obj, "model_dump"):  # pydantic
        return obj.model_dump()
    if hasattr(obj, "__dict__"):
        return vars(obj)
    return obj  # primitives fine
 
def serialise(data):
    if isinstance(data, (list, tuple)):
        return [serialise(x) for x in data]
    if isinstance(data, dict):
        return {k: serialise(v) for k, v in data.items()}
    return make_serialisable(data)

# ──────────────────────────────────
# Chat UI Helper Functions
# ──────────────────────────────────
def display_tool_call(tool_call: ToolCall):
    """Display a tool call in an attractive format"""
    with st.expander(f"🛠️ Tool Call: **{tool_call.name}**", expanded=True):
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.subheader("📥 Arguments")
            st.json(tool_call.arguments)
        
        with col2:
            st.subheader("📤 Result")
            if tool_call.success:
                st.success("✅ Success")
                st.json(tool_call.result)
            else:
                st.error("❌ Failed")
                st.error(tool_call.result.get("error", "Unknown error"))
        
        st.caption(f"⏰ Executed at: {tool_call.timestamp}")

def display_chat_message(message: ChatMessage):
    """Display a chat message with proper formatting"""
    timestamp = message.timestamp
    
    if message.role == "user":
        with st.chat_message("user"):
            st.write(message.content)
            st.caption(f"🕒 {timestamp}")
    
    elif message.role == "assistant":
        with st.chat_message("assistant"):
            st.write(message.content)
            
            # Show tool calls if any
            if message.tool_calls:
                st.subheader("🔧 Tools Used")
                for tool_call in message.tool_calls:
                    display_tool_call(tool_call)
            
            st.caption(f"🕒 {timestamp}")

def get_timestamp():
    """Get current timestamp in a readable format"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def fallback_prompt(app_id: str) -> str:
    return f"""You are an intelligent assistant that helps users interact with Algolia search engine through various tools.

You have access to comprehensive Algolia MCP tools that allow you to:
- Search and browse indices
- Manage search data (add, update, delete records)
- Configure search settings and rules
- Analyze search performance and metrics
- Work with synonyms and query suggestions

Instructions:
1. Always include "applicationId": "{app_id}" in every tool call
2. Be conversational and helpful in your responses
3. Explain what tools you're using and why
4. Provide clear summaries of the results
5. Ask follow-up questions when appropriate
6. If you need more information, ask the user for clarification

When a user asks about Algolia functionality, choose the most appropriate tool(s) and explain your reasoning.
"""
 
import os, json, asyncio, threading, time
from contextlib import AsyncExitStack
from typing import Dict, Any, List, Optional
 
import streamlit as st
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
 
 
########################################################################
# ---------- MCP CLIENT (unchanged API names, adds applicationId) ---- #
########################################################################
 
class AlgoliaMCPClient:
    def __init__(self, mcp_node_path: Optional[str] = None):
        load_dotenv()
        self.app_id  = os.getenv("ALGOLIA_APP_ID")
        self.api_key = os.getenv("ALGOLIA_API_KEY")
        self.mcp_path = mcp_node_path or os.getenv("MCP_NODE_PATH", "./mcp-node")
        if not all([self.app_id, self.api_key]):
            raise RuntimeError("ALGOLIA_APP_ID and ALGOLIA_API_KEY missing")
        self.exit_stack = AsyncExitStack()
        self.tools: list = []
        self.session = None
        self.loop: asyncio.AbstractEventLoop = None
 
    # ---------- event-loop helpers ----------
    def _ensure_loop(self):
        if self.loop is None:
            self.loop = asyncio.new_event_loop()
            threading.Thread(target=self.loop.run_forever, daemon=True).start()
 
    def run_async(self, awaitable):
        self._ensure_loop()
        fut = asyncio.run_coroutine_threadsafe(awaitable, self.loop)
        return fut.result()
 
    # ---------- connection ----------
    async def connect(self) -> bool:
        try:
            params = StdioServerParameters(
                command="node",
                args=["--experimental-strip-types", "--no-warnings=ExperimentalWarning", "src/app.ts"],
                cwd=self.mcp_path,
                env={"ALGOLIA_APP_ID": self.app_id, "ALGOLIA_API_KEY": self.api_key},
            )
            read, write = await self.exit_stack.enter_async_context(stdio_client(params))
            self.session = await self.exit_stack.enter_async_context(ClientSession(read, write))
            await self.session.initialize()
            self.tools = (await self.session.list_tools()).tools
            return True
        except Exception as e:
            st.error(f"MCP connect error: {e}")
            return False
 
    async def call_tool(self, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            res = await self.session.call_tool(tool, arguments=args)
            return {"success": True, "content": res.content}
        except Exception as e:
            return {"success": False, "error": str(e)}
 
    # ---------- convenience wrappers with correct names ----------
    async def get_user(self):            return await self.call_tool("getUserInfo", {})
    async def get_apps(self):            return await self.call_tool("getApplications", {})
    async def list_indices(self, app_id):   return await self.call_tool("listIndices", {"applicationId": app_id})
    async def get_settings(self, app_id, index):
        return await self.call_tool("getSettings", {"applicationId": app_id, "indexName": index})
    async def search(self, app_id, index, query, hits=20, page=0):
        return await self.call_tool("searchSingleIndex", {  
                                                            "applicationId": app_id,
                                                            "indexName": index,
                                                            "requestBody": {
                                                                "query": query,
                                                                "hitsPerPage": hits,
                                                                "page": page
                                                            }
                                                        })
    async def save_obj(self, app_id, index, obj):
        return await self.call_tool("saveObject",
                                    {"applicationId": app_id, "indexName": index, "requestBody": obj})
    async def p_update(self, app_id, index, obj_id, partial):
        return await self.call_tool("partialUpdateObject",
                                    {"applicationId": app_id, "indexName": index,
                                     "objectID": obj_id, "partialObject": partial})
    async def batch(self, app_id, index, ops):
        return await self.call_tool("batch",
                                    {"applicationId": app_id, "index": index, "requests": ops})
    async def top_searches(self, app_id, index, start, end):
        return await self.call_tool("getTopSearches",
                                    {"applicationId": app_id, "index": index,
                                     "startDate": start, "endDate": end, "region": "europe-germany"})
    async def no_results_rate(self, app_id, index, start, end):
        return await self.call_tool("getNoResultsRate",
                                    {"applicationId": app_id, "index": index,
                                     "startDate": start, "endDate": end})
 
    async def disconnect(self):
        try:
            # Close session first if it exists
            if self.session:
                try:
                    await self.session.close()
                except Exception:
                    pass  # Ignore session close errors
                self.session = None
            
            # Try to close exit stack, but handle context errors gracefully
            try:
                await self.exit_stack.aclose()
            except RuntimeError as e:
                if "cancel scope" in str(e) or "different task" in str(e):
                    # Context error - cleanup manually
                    self.exit_stack = AsyncExitStack()  # Reset the exit stack
                else:
                    raise  # Re-raise if it's a different error
            
            # Reset tools
            self.tools = []
            
            # Stop the event loop if it's running
            if self.loop and self.loop.is_running():
                try:
                    self.loop.call_soon_threadsafe(self.loop.stop)
                except Exception:
                    pass  # Ignore if loop is already stopped
            
            self.loop = None
            
        except Exception as e:
            # If all else fails, just reset everything
            self.session = None
            self.tools = []
            self.exit_stack = AsyncExitStack()
            self.loop = None
            # Don't raise the error, just log it
            print(f"Warning: Disconnect cleanup error (ignored): {e}")

def show_search_results(res: Dict[str, Any]):
    """Display search results with proper highlighting and better key-value alignment"""
    if not res.get("success"):
        st.error(res.get("error", "Unknown error"))
        return
    
    for content_item in res.get("content", []):
        text_content = getattr(content_item, "text", None) or str(content_item)
        try:
            search_data = json.loads(text_content)
            
            # Extract search metadata
            hits = search_data.get("hits", [])
            nb_hits = search_data.get("nbHits", 0)
            processing_time = search_data.get("processingTimeMS", 0)
            query = search_data.get("query", "")
            page = search_data.get("page", 0)
            hits_per_page = search_data.get("hitsPerPage", 20)
            
            # Display search summary
            st.markdown("### 🔍 Search Results")
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Results", f"{nb_hits:,}")
            with col2:
                st.metric("Processing Time", f"{processing_time}ms")
            with col3:
                st.metric("Current Page", page + 1)
            with col4:
                st.metric("Results Shown", len(hits))
            
            # Add color legend for match indicators right after metrics
            st.markdown("**🎯 Match Levels:** 🟢 Full Match  •  🟡 Partial Match  •  ⚪ No Match")
            
            st.markdown("---")
            
            if not hits:
                st.warning("🔍 No results found for your query")
                st.info("💡 Try different keywords or check spelling")
                return
            
            # Display each hit
            for i, hit in enumerate(hits, 1):
                st.markdown(f"### 📄 **Result {i}**")
                
                with st.container():
                    # Show objectID prominently
                    object_id = hit.get("objectID", "Unknown")
                    st.markdown(f"**🆔 Object ID:** `{object_id}`")
                    
                    # Display highlighted results if available
                    highlight_result = hit.get("_highlightResult", {})
                    
                    if highlight_result:
                        for field_name, highlight_data in highlight_result.items():
                            if isinstance(highlight_data, dict) and "value" in highlight_data:
                                highlighted_value = highlight_data.get("value", "")
                                match_level = highlight_data.get("matchLevel", "none")
                                
                                # Create a more structured display with better alignment
                                col1, col2, col3 = st.columns([1.5, 0.3, 3])
                                
                                with col1:
                                    st.markdown(f"**{field_name}:**")
                                
                                with col2:
                                    # Show match level with color coding
                                    if match_level == "full":
                                        st.markdown("🟢")
                                    elif match_level == "partial":
                                        st.markdown("🟡")
                                    else:
                                        st.markdown("⚪")
                                
                                with col3:
                                    # Render highlighted text by converting <em> tags to styled HTML
                                    if "<em>" in highlighted_value and "</em>" in highlighted_value:
                                        # Convert <em> tags to highlighted HTML with background color
                                        highlighted_html = highlighted_value.replace(
                                            "<em>", 
                                            '<span style="background-color: #ffeb3b; color: #000; padding: 2px 4px; border-radius: 3px; font-weight: bold;">'
                                        ).replace("</em>", "</span>")
                                        st.markdown(highlighted_html, unsafe_allow_html=True)
                                    else:
                                        st.markdown(highlighted_value)
                        
                        st.markdown("---")
                
                # Add separator between results
                if i < len(hits):
                    st.markdown("---")
            
            # Pagination info
            if nb_hits > hits_per_page:
                total_pages = (nb_hits + hits_per_page - 1) // hits_per_page
                st.info(f"📖 **Page {page + 1} of {total_pages}** | Use the 'Page' input above to navigate")
        
        except (json.JSONDecodeError, TypeError) as e:
            st.error(f"❌ Error parsing search results: {e}")
            # Fallback to original display
            show(search_data)
 
 
###############################################
# ---------- STREAMLIT UI ------------------- #
###############################################
 
st.set_page_config(
    page_title="Algolia MCP Client", 
    page_icon="🔍", 
    layout="wide",
    initial_sidebar_state="expanded"
)
 
def init_state():
    defaults = {
        "client": None, "connected": False,
        "apps": [], "current_app": None,
        "app_data": {},  # Store mapping of app names to app IDs
        "indices": []
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    return defaults
init_state()
 
# ---------- sidebar ----------
with st.sidebar:
    st.header("🔌 MCP Server Connection")
    st.caption("Connect to Algolia via Model Context Protocol (MCP) server")
    
    if not st.session_state.connected:
        if st.button("🚀 Connect to MCP Server", type="primary"):
            with st.spinner("🔄 Establishing connection to MCP server..."):
                st.session_state.client = AlgoliaMCPClient()
                if st.session_state.client.run_async(st.session_state.client.connect()):
                    st.session_state.connected = True
                    # fetch apps immediately
                    raw = st.session_state.client.run_async(st.session_state.client.get_apps())
                    apps = []
                    app_data = {}
                    
                    for item in raw.get("content", []):
                        # Get the text content from the item
                        text_content = getattr(item, "text", None) or str(item)
                        
                        try:
                            # Parse the JSON to extract app info
                            app_json = json.loads(text_content)
                            app_list = app_json.get("data", [])
                            
                            for app_info in app_list:
                                app_id = app_info.get("id")
                                app_name = app_info.get("attributes", {}).get("name", f"App {app_id}")
                                
                                if app_name and app_id:
                                    apps.append(app_name)
                                    app_data[app_name] = app_id
                                    
                        except (json.JSONDecodeError, TypeError, AttributeError):
                            # Fallback: if parsing fails, use the raw content
                            apps.append(str(text_content)[:50] + "..." if len(str(text_content)) > 50 else str(text_content))
                    
                    st.session_state.apps = apps
                    st.session_state.app_data = app_data
                    st.session_state.current_app = apps[0] if apps else None
                    
                    # Success message with more details
                    st.success(f"✅ MCP Server connection successful!")
                    st.info(f"🎯 Found {len(apps)} Algolia application(s) in your account")
                    # Trigger a rerun to refresh the UI and show the connected state
                    st.rerun()
                else:
                    st.error("❌ MCP Server connection failed")
                    st.warning("Please check your Algolia credentials and MCP server status")
    else:
        st.success("✅ MCP Server Connected")
        st.caption("Ready to interact with Algolia APIs")
        if st.button("🔌 Disconnect from MCP Server"):
            with st.spinner("🔄 Disconnecting from MCP server..."):
                try:
                    # Attempt graceful disconnect
                    st.session_state.client.run_async(st.session_state.client.disconnect())
                except Exception as e:
                    # If disconnect fails, still proceed with cleanup
                    st.warning(f"Disconnect warning: {str(e)[:100]}... (connection cleaned up)")
                
                # Reset session state regardless of disconnect success
                for k in ["connected", "client", "apps", "current_app", "app_data", "indices"]:
                    st.session_state[k] = init_state()[k]
                
                st.success("🔌 Successfully disconnected from MCP Server")
                time.sleep(0.5)  # Brief pause for user feedback
            st.rerun()
 
    if st.session_state.apps:
        st.markdown("---")
        st.subheader("🎯 Application Selection")
        selected_app = st.selectbox(
            "Choose your Algolia application:",
            st.session_state.apps,
                     index=st.session_state.apps.index(st.session_state.current_app or st.session_state.apps[0]),
            key="current_app",
            help="Select which Algolia application you want to work with"
        )
        

 
# ---------- helper ----------
def show(res: Dict[str, Any]):
    if res.get("success"):
        for c in res["content"]:
            txt = getattr(c, "text", None)
            if txt:
                try:
                    st.json(json.loads(txt))
                except Exception:
                    st.write(txt)
            else:
                st.json(c)
    else:
        st.error(res.get("error", "Unknown error"))
 
# Add main page header
st.title("🔍 Algolia MCP Client")
st.markdown("**Model Context Protocol (MCP) interface for Algolia Search**")

# Connection status indicator
if st.session_state.connected:
    st.success(f"🟢 **Connected to MCP Server** | Active App: **{st.session_state.current_app}**")
else:
    st.warning("🟡 **Not Connected** | Please connect to MCP Server in sidebar")

st.markdown("---")
 
if not st.session_state.connected:
    st.warning("💡 The MCP Server enables communication with Algolia APIs")
    st.stop()
 
# Get the current app name and lookup its ID
app = st.session_state.current_app
app_id = st.session_state.app_data.get(app, None)

if not app_id:
    st.error("❌ Could not find application ID for selected app")
    st.stop()
 
#################################################
# ----------------- TABS ---------------------- #
#################################################
 
# Custom CSS to make tabs bigger
st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    
    .stTabs [data-baseweb="tab"] {
        height: 60px;
        padding-left: 20px;
        padding-right: 20px;
        background-color: rgba(255, 255, 255, 0.05);
        border-radius: 8px;
        color: #FAFAFA;
        font-size: 20px;
        font-weight: 500;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.3s ease;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: rgba(255, 75, 75, 0.2);
        color: #FF4B4B;
        font-size: 20px;
        font-weight: 600;
        border: 1px solid rgba(255, 75, 75, 0.3);
    }
    
    .stTabs [data-baseweb="tab"]:hover {
        background-color: rgba(255, 255, 255, 0.1);
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
    }
</style>
""", unsafe_allow_html=True)

tab1, tab2, tab3, tab6, tab7 = st.tabs(
    ["👤 User & Apps", "📊 Indices", "🔍 Search", "📤 Upload Data", "🤖 AI Chat"]
)
 
with tab1:
    st.subheader("Account")
    if st.button("Get user info"):
        # Add timing for get user info
        import time
        start_time = time.time()
        
        result = st.session_state.client.run_async(st.session_state.client.get_user())
        
        end_time = time.time()
        duration = end_time - start_time
        time_str = f"{duration*1000:.0f} milliseconds" if duration < 1 else f"{duration:.2f} seconds"
        
        # Display user info in an attractive format
        if result.get("success"):
            # Extract user data from the result
            user_data = None
            for content_item in result.get("content", []):
                text_content = getattr(content_item, "text", None) or str(content_item)
                try:
                    user_json = json.loads(text_content)
                    
                    # Handle different response formats
                    if isinstance(user_json, dict):
                        # Standard format: {"data": {...}}
                        user_data = user_json.get("data", {})
                        if not user_data and "id" in user_json:
                            # Alternative format: direct user object
                            user_data = user_json
                    elif isinstance(user_json, list) and len(user_json) > 0:
                        # Array format: [{"data": {...}}] or [user_object]
                        first_item = user_json[0]
                        if isinstance(first_item, dict):
                            user_data = first_item.get("data", first_item)
                    
                    # If we found valid user data, break out of loop
                    if user_data and isinstance(user_data, dict):
                        break
                        
                except (json.JSONDecodeError, TypeError) as e:
                    st.warning(f"⚠️ Could not parse user data: {e}")
                    continue
            
            if user_data:
                # Display user info in a beautiful card format
                st.markdown("### 👤 Your Account Information")
                
                # Create main info card
                with st.container():
                    col1, col2 = st.columns([1, 2])
                    
                    with col1:
                        # Avatar section
                        avatar_url = user_data.get("attributes", {}).get("avatar", {}).get("64", "")
                        if avatar_url:
                            st.image(avatar_url, width=100, caption="Profile Picture")
                        else:
                            st.markdown("### 👤")
                            st.caption("No profile picture")
                    
                    with col2:
                        # User details
                        attributes = user_data.get("attributes", {})
                        
                        # Email
                        email = attributes.get("email", "Not available")
                        st.markdown(f"**📧 Email:** {email}")
                        
                        # Full name
                        full_name = attributes.get("full_name")
                        if full_name:
                            st.markdown(f"**👤 Name:** {full_name}")
                        else:
                            st.markdown("**👤 Name:** *Not set*")
                        
                        # User ID
                        user_id = user_data.get("id", "Unknown")
                        st.markdown(f"**🆔 User ID:** `{user_id}`")
                        
                        # Account type
                        user_type = user_data.get("type", "Unknown").title()
                        st.markdown(f"**🏷️ Account Type:** {user_type}")
                        
                        # Last updated
                        updated_at = attributes.get("updated_at", "")
                        if updated_at:
                            try:
                                from datetime import datetime
                                updated_dt = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                                formatted_date = updated_dt.strftime('%B %d, %Y at %H:%M UTC')
                                st.markdown(f"**🔄 Last Updated:** {formatted_date}")
                            except:
                                st.markdown(f"**🔄 Last Updated:** {updated_at}")
                        
                        # API call timing
                        st.markdown(f"**⚡ Retrieved in:** {time_str}")
                
            else:
                st.error("❌ Could not parse user information")
                st.json(result)  # Fallback to raw display
            
            st.toast(f"👤 User info retrieved in {time_str}!", icon="👋")
        
        else:
            st.error("❌ Failed to retrieve user information")
            st.error(result.get("error", "Unknown error"))
    st.subheader("Applications")
    st.write(f"Active application: **{app}**")
    st.write(f"Application ID: `{app_id}`")
    
    with st.expander("📋 All Applications", expanded=False):
        if st.session_state.apps:
            st.write("Available applications:")
            for app_name in st.session_state.apps:
                app_id_display = st.session_state.app_data.get(app_name, "N/A")
                st.write(f"• **{app_name}** (ID: `{app_id_display}`)")
        else:
            st.write("No applications found")
 
with tab2:
    st.subheader("📊 Indices Management")
    
    # Initialize indices in session state if not present
    if 'indices_data' not in st.session_state:
        st.session_state.indices_data = []
    if 'indices_names' not in st.session_state:
        st.session_state.indices_names = []
    
    # Load Indices Section
    col1, col2 = st.columns([2, 1])
    
    with col1:
        if st.button("🔄 Load All Indices", type="primary"):
            with st.spinner("Loading indices..."):
                # Add timing for list indices
                import time
                start_time = time.time()
                
                res = st.session_state.client.run_async(st.session_state.client.list_indices(app_id))
                
                end_time = time.time()
                duration = end_time - start_time
                time_str = f"{duration*1000:.0f} milliseconds" if duration < 1 else f"{duration:.2f} seconds"
                
                if res.get("success"):
                    # Parse indices data
                    indices_raw = res.get("content", [])
                    indices_data = []
                    
                    for item in indices_raw:
                        # Get the text content from the item
                        text_content = getattr(item, "text", None) or str(item)
                        
                        try:
                            # Parse the JSON to extract indices info
                            indices_json = json.loads(text_content)
                            indices_list = indices_json.get("items", [])
                            indices_data.extend(indices_list)
                        except (json.JSONDecodeError, TypeError, AttributeError):
                            # Fallback: if parsing fails, try the item directly
                            if isinstance(item, dict):
                                indices_data.append(item)
                    
                    st.session_state.indices_data = indices_data
                    st.session_state.indices_names = [idx.get("name", "Unknown") for idx in indices_data]
                    
                    st.toast(f"📋 {len(indices_data)} indices loaded in {time_str}!", icon="📂")
                    st.success(f"✅ Found {len(indices_data)} indices in your application")
                else:
                    st.error("❌ Failed to load indices")
                    st.error(res.get("error", "Unknown error"))
    
    with col2:
        if st.session_state.indices_data:
            st.metric("Total Indices", len(st.session_state.indices_data))
    
    # Display Indices Section
    if st.session_state.indices_data:
        st.markdown("---")
        st.subheader("📋 Your Indices")
        
        # Create a tabular view of all indices
        st.markdown("### 📊 All Indices Overview")
        
        # Prepare data for the table
        table_data = []
        for idx in st.session_state.indices_data:
            # Calculate sizes in MB
            data_size_mb = idx.get("dataSize", 0) / (1024 * 1024) if idx.get("dataSize", 0) > 0 else 0
            file_size_mb = idx.get("fileSize", 0) / (1024 * 1024) if idx.get("fileSize", 0) > 0 else 0
            
            # Format timestamps
            created_at = idx.get("createdAt", "")
            updated_at = idx.get("updatedAt", "")
            
            try:
                from datetime import datetime
                if created_at:
                    created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    created_formatted = created_dt.strftime('%Y-%m-%d %H:%M')
                else:
                    created_formatted = "Unknown"
                    
                if updated_at:
                    updated_dt = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                    updated_formatted = updated_dt.strftime('%Y-%m-%d %H:%M')
                else:
                    updated_formatted = "Unknown"
            except:
                created_formatted = created_at[:16] if created_at else "Unknown"
                updated_formatted = updated_at[:16] if updated_at else "Unknown"
            
            # Status
            pending_task = idx.get("pendingTask", False)
            status = "🟡 Processing" if pending_task else "🟢 Ready"
            
            table_data.append({
                "Index Name": idx.get("name", "Unknown"),
                "Records": f"{idx.get('entries', 0):,}",
                "Data Size": f"{data_size_mb:.2f} MB",
                "File Size": f"{file_size_mb:.2f} MB",
                "Status": status,
                "Created": created_formatted,
                "Updated": updated_formatted,
                "Pending Tasks": idx.get("numberOfPendingTasks", 0)
            })
        
        # Display the table
        if table_data:
            import pandas as pd
            df = pd.DataFrame(table_data)
            
            # Display with custom styling
            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Index Name": st.column_config.TextColumn("🏷️ Index Name", width="medium"),
                    "Records": st.column_config.TextColumn("📝 Records", width="small"),
                    "Data Size": st.column_config.TextColumn("💾 Data Size", width="small"),
                    "File Size": st.column_config.TextColumn("📁 File Size", width="small"),
                    "Status": st.column_config.TextColumn("⚙️ Status", width="small"),
                    "Created": st.column_config.TextColumn("📅 Created", width="medium"),
                    "Updated": st.column_config.TextColumn("🔄 Updated", width="medium"),
                    "Pending Tasks": st.column_config.NumberColumn("⏳ Tasks", width="small")
                }
            )
            
            # Add summary metrics below the table
            st.markdown("### 📈 Summary Statistics")
            col1, col2, col3, col4 = st.columns(4)
            
            total_records = sum(idx.get("entries", 0) for idx in st.session_state.indices_data)
            total_data_size = sum(idx.get("dataSize", 0) for idx in st.session_state.indices_data) / (1024 * 1024)
            total_file_size = sum(idx.get("fileSize", 0) for idx in st.session_state.indices_data) / (1024 * 1024)
            processing_indices = sum(1 for idx in st.session_state.indices_data if idx.get("pendingTask", False))
            
            with col1:
                st.metric("🗂️ Total Indices", len(st.session_state.indices_data))
            with col2:
                st.metric("📝 Total Records", f"{total_records:,}")
            with col3:
                st.metric("💾 Total Data Size", f"{total_data_size:.2f} MB")
            with col4:
                st.metric("🟡 Processing", processing_indices)
        
        st.markdown("---")
        
        # Initialize session state for detailed view
        if 'show_detailed_view' not in st.session_state:
            st.session_state.show_detailed_view = False
        
        # Header with button to toggle detailed view
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown("### 🔍 Detailed Index View")
        with col2:
            if st.button("📋 Select Index", key="show_detailed_view_btn", type="primary"):
                st.session_state.show_detailed_view = not st.session_state.show_detailed_view
        
        # Show index selection dropdown only when button is clicked
        if st.session_state.show_detailed_view:
            selected_index_name = st.selectbox(
                "Choose an index to view detailed settings:",
                options=st.session_state.indices_names,
                key="selected_index",
                help="Select an index to view its detailed settings and configuration"
            )
            
            # Show details automatically when an index is selected
            if selected_index_name:
                # Find the selected index data
                selected_index = None
                for idx in st.session_state.indices_data:
                    if idx.get("name") == selected_index_name:
                        selected_index = idx
                        break
                
                if selected_index:
                    # Display index information in a user-friendly way
                    st.markdown(f"### 📊 Index: **{selected_index_name}**")
                    
                    # Create columns for metrics
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        entries = selected_index.get("entries", 0)
                        st.metric("📝 Records", f"{entries:,}")
                    
                    with col2:
                        data_size = selected_index.get("dataSize", 0)
                        size_mb = data_size / (1024 * 1024) if data_size > 0 else 0
                        st.metric("💾 Data Size", f"{size_mb:.2f} MB")
                    
                    with col3:
                        file_size = selected_index.get("fileSize", 0)
                        file_mb = file_size / (1024 * 1024) if file_size > 0 else 0
                        st.metric("📁 File Size", f"{file_mb:.2f} MB")
                    
                    with col4:
                        pending_tasks = selected_index.get("numberOfPendingTasks", 0)
                        st.metric("⏳ Pending Tasks", pending_tasks)
                    
                    # Additional Information
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown("**📅 Timestamps:**")
                        created_at = selected_index.get("createdAt", "Unknown")
                        updated_at = selected_index.get("updatedAt", "Unknown")
                        
                        if created_at != "Unknown":
                            try:
                                from datetime import datetime
                                created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                                st.write(f"**Created:** {created_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                            except:
                                st.write(f"**Created:** {created_at}")
                        
                        if updated_at != "Unknown":
                            try:
                                from datetime import datetime
                                updated_dt = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                                st.write(f"**Updated:** {updated_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                            except:
                                st.write(f"**Updated:** {updated_at}")
                    
                    with col2:
                        st.markdown("**⚙️ Status:**")
                        pending_task = selected_index.get("pendingTask", False)
                        last_build_time = selected_index.get("lastBuildTimeS", 0)
                        
                        status_color = "🟢" if not pending_task else "🟡"
                        status_text = "Ready" if not pending_task else "Processing"
                        st.write(f"**Status:** {status_color} {status_text}")
                        st.write(f"**Last Build:** {last_build_time}s")
                
                # Sample Records Section
                st.markdown("---")
                st.markdown("### 📄 **Sample Records**")
                
                # Initialize session state for sample data
                if f'sample_data_{selected_index_name}' not in st.session_state:
                    st.session_state[f'sample_data_{selected_index_name}'] = None
                
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.markdown("Preview actual data stored in this index:")
                with col2:
                    if st.button(f"🔍 Load Sample Data", key="load_sample_btn"):
                        with st.spinner(f"Loading sample data from {selected_index_name}..."):
                            # Add timing for sample data loading
                            import time
                            start_time = time.time()
                            
                            # Fetch sample records using search with empty query
                            sample_result = st.session_state.client.run_async(
                                st.session_state.client.search(app_id, selected_index_name, "", 2, 0))
                            
                            end_time = time.time()
                            duration = end_time - start_time
                            time_str = f"{duration*1000:.0f} milliseconds" if duration < 1 else f"{duration:.2f} seconds"
                            
                            if sample_result.get("success"):
                                # Parse the sample data
                                sample_records = []
                                search_data_info = {}
                                for content_item in sample_result.get("content", []):
                                    text_content = getattr(content_item, "text", None) or str(content_item)
                                    try:
                                        search_data = json.loads(text_content)
                                        hits = search_data.get("hits", [])
                                        sample_records.extend(hits)
                                        search_data_info = search_data  # Store for total hits info
                                    except (json.JSONDecodeError, TypeError):
                                        continue
                                
                                # Store sample data in session state
                                st.session_state[f'sample_data_{selected_index_name}'] = {
                                    'records': sample_records,
                                    'total_hits': search_data_info.get("nbHits", "Unknown"),
                                    'load_time': time_str
                                }
                                
                                if sample_records:
                                    st.success(f"📊 Found {len(sample_records)} sample record(s)")
                                    st.toast(f"📄 Sample data loaded in {time_str}!", icon="📋")
                                else:
                                    st.warning("📄 No records found in this index")
                                    st.info("The index might be empty or all records might be filtered out")
                            else:
                                st.error("❌ Failed to load sample data")
                                st.error(sample_result.get("error", "Unknown error"))
                
                # Display sample records outside of columns for proper centering
                sample_data = st.session_state.get(f'sample_data_{selected_index_name}')
                
                if sample_data and sample_data['records']:
                    st.markdown("---")
                    
                    # Display sample records in full-width centered layout
                    for i, record in enumerate(sample_data['records'][:2], 1):  # Show max 2 records
                        st.markdown(f"#### 📝 **Record {i}:**")
                        
                        # Create expandable view for each record
                        with st.expander(f"View Record {i} Details", expanded=i==1):
                            # Remove Algolia metadata for cleaner display
                            clean_record = {k: v for k, v in record.items() 
                                          if not k.startswith('_') and k != 'objectID'}
                            
                            if clean_record:
                                # Display key-value pairs in a nice format
                                col1, col2 = st.columns([1, 2])
                                
                                for key, value in list(clean_record.items())[:8]:  # Show first 8 fields
                                    with col1:
                                        st.markdown(f"**{key}:**")
                                    with col2:
                                        if isinstance(value, str) and len(value) > 100:
                                            st.markdown(f"`{value[:100]}...`")
                                        elif isinstance(value, (list, dict)):
                                            st.json(value)
                                        else:
                                            st.markdown(f"`{value}`")
                                
                                # Show total field count
                                total_fields = len(record)
                                if total_fields > 8:
                                    st.info(f"📊 **Total fields in record:** {total_fields} (showing first 8)")
                                else:
                                    st.info(f"📊 **Total fields in record:** {total_fields}")
                                
                                # Object ID (always show this)
                                if 'objectID' in record:
                                    st.markdown(f"**🆔 Object ID:** `{record['objectID']}`")
                                
                                # Raw record expandable
                                with st.expander("🔍 Raw Record Data", expanded=False):
                                    st.json(record)
                            else:
                                st.info("📄 Record contains only metadata")
                                st.json(record)
                        
                        if i < len(sample_data['records']):
                            st.markdown("---")
                    
                    # Additional info
                    total_hits = sample_data['total_hits']
                    if total_hits != "Unknown":
                        st.info(f"💡 **This index contains {total_hits:,} total records.** Showing sample from the first {len(sample_data['records'])}.")
                
                elif sample_data and not sample_data['records']:
                    st.markdown("---")
                    st.warning("📄 No records found in this index")
                    st.info("The index might be empty or all records might be filtered out")
                
                else:
                    # Show helpful message when sample not loaded
                    st.info("👆 Click '🔍 Load Sample Data' to see what data is stored in this index")
                
                # Get Settings Button
                st.markdown("---")
                if st.button(f"⚙️ Get Settings for '{selected_index_name}'", key="get_settings_btn"):
                    with st.spinner(f"Loading settings for {selected_index_name}..."):
                        # Add timing for get settings
                        import time
                        start_time = time.time()
                        
                        result = st.session_state.client.run_async(st.session_state.client.get_settings(app_id, selected_index_name))
                        
                        end_time = time.time()
                        duration = end_time - start_time
                        time_str = f"{duration*1000:.0f} milliseconds" if duration < 1 else f"{duration:.2f} seconds"
                        
                        if result.get("success"):
                            st.toast(f"⚙️ Settings retrieved in {time_str}!", icon="🔧")
                            
                            # Display settings in a more readable format
                            st.subheader(f"⚙️ Settings for {selected_index_name}")
                            
                            for content_item in result.get("content", []):
                                text_content = getattr(content_item, "text", None) or str(content_item)
                                try:
                                    settings_data = json.loads(text_content)
                                    
                                    # Display key settings in tabs
                                    setting_tab1, setting_tab2, setting_tab3 = st.tabs(["🔍 Search", "📊 Attributes", "🛠️ Advanced"])
                                    
                                    with setting_tab1:
                                        st.markdown("### 🔍 **Search Configuration**")
                                        
                                        # Searchable Attributes
                                        searchable_attrs = settings_data.get("searchableAttributes", [])
                                        st.markdown("**🎯 Searchable Attributes:**")
                                        if searchable_attrs:
                                            for i, attr in enumerate(searchable_attrs, 1):
                                                st.markdown(f"  **{i}.** `{attr}`")
                                        else:
                                            st.info("📝 All attributes are searchable (default behavior)")
                                        
                                        st.markdown("---")
                                        
                                        # Highlight Attributes
                                        highlight_attrs = settings_data.get("attributesToHighlight", [])
                                        st.markdown("**✨ Attributes to Highlight:**")
                                        if highlight_attrs and highlight_attrs != [None]:
                                            for attr in highlight_attrs:
                                                if attr:
                                                    st.markdown(f"  • `{attr}`")
                                        else:
                                            st.info("🔍 No specific highlighting configured")
                                        
                                        st.markdown("---")
                                        
                                        # Snippet Attributes
                                        snippet_attrs = settings_data.get("attributesToSnippet", [])
                                        st.markdown("**📄 Attributes to Snippet:**")
                                        if snippet_attrs and snippet_attrs != [None]:
                                            for attr in snippet_attrs:
                                                if attr:
                                                    st.markdown(f"  • `{attr}`")
                                        else:
                                            st.info("📋 No snippet configuration")
                                    
                                    with setting_tab2:
                                        st.markdown("### 📊 **Attributes & Ranking**")
                                        
                                        # Faceting Attributes
                                        faceting_attrs = settings_data.get("attributesForFaceting", [])
                                        st.markdown("**🏷️ Faceting Attributes:**")
                                        if faceting_attrs:
                                            for attr in faceting_attrs:
                                                st.markdown(f"  • `{attr}`")
                                        else:
                                            st.info("🔍 No faceting attributes configured")
                                        
                                        st.markdown("---")
                                        
                                        # Ranking
                                        ranking = settings_data.get("ranking", [])
                                        st.markdown("**🎯 Ranking Formula:**")
                                        if ranking:
                                            for i, rank_rule in enumerate(ranking, 1):
                                                if rank_rule.startswith("typo"):
                                                    icon = "⌨️"
                                                    desc = "Typo tolerance"
                                                elif rank_rule.startswith("geo"):
                                                    icon = "📍"
                                                    desc = "Geographic distance"
                                                elif rank_rule.startswith("words"):
                                                    icon = "📝"
                                                    desc = "Word matching"
                                                elif rank_rule.startswith("filters"):
                                                    icon = "🔍"
                                                    desc = "Filter matching"
                                                elif rank_rule.startswith("proximity"):
                                                    icon = "📐"
                                                    desc = "Word proximity"
                                                elif rank_rule.startswith("attribute"):
                                                    icon = "🎯"
                                                    desc = "Attribute importance"
                                                elif rank_rule.startswith("exact"):
                                                    icon = "✅"
                                                    desc = "Exact matching"
                                                elif rank_rule.startswith("custom"):
                                                    icon = "⚙️"
                                                    desc = "Custom ranking"
                                                else:
                                                    icon = "📊"
                                                    desc = "Ranking rule"
                                                
                                                st.markdown(f"  **{i}.** {icon} **{rank_rule}** - *{desc}*")
                                        else:
                                            st.info("📈 Using default ranking formula")
                                        
                                        st.markdown("---")
                                        
                                        # Custom Ranking
                                        custom_ranking = settings_data.get("customRanking", [])
                                        st.markdown("**⚙️ Custom Ranking Attributes:**")
                                        if custom_ranking:
                                            for i, custom_rule in enumerate(custom_ranking, 1):
                                                if custom_rule.startswith("desc("):
                                                    direction = "📉 Descending"
                                                    attr = custom_rule[5:-1]  # Remove desc( and )
                                                elif custom_rule.startswith("asc("):
                                                    direction = "📈 Ascending"
                                                    attr = custom_rule[4:-1]  # Remove asc( and )
                                                else:
                                                    direction = "📊"
                                                    attr = custom_rule
                                                
                                                st.markdown(f"  **{i}.** {direction} `{attr}`")
                                        else:
                                            st.info("🎯 No custom ranking configured")
                                    
                                    with setting_tab3:
                                        st.markdown("### 🛠️ **Advanced Settings**")
                                        
                                        # Show all other settings in a nice format
                                        advanced_settings = {k: v for k, v in settings_data.items() 
                                                           if k not in ["searchableAttributes", "attributesToHighlight", 
                                                                       "attributesToSnippet", "attributesForFaceting", 
                                                                       "ranking", "customRanking"]}
                                        
                                        if advanced_settings:
                                            # Group settings by type
                                            search_settings = {}
                                            performance_settings = {}
                                            other_settings = {}
                                            
                                            for key, value in advanced_settings.items():
                                                if any(word in key.lower() for word in ['typo', 'language', 'query', 'alternative', 'synonym']):
                                                    search_settings[key] = value
                                                elif any(word in key.lower() for word in ['timeout', 'max', 'min', 'limit', 'numericattributes']):
                                                    performance_settings[key] = value
                                                else:
                                                    other_settings[key] = value
                                            
                                            # Display search-related settings
                                            if search_settings:
                                                st.markdown("**🔍 Search Behavior:**")
                                                for key, value in search_settings.items():
                                                    if isinstance(value, bool):
                                                        icon = "✅" if value else "❌"
                                                        st.markdown(f"  • **{key}**: {icon}")
                                                    elif isinstance(value, (list, dict)) and len(str(value)) > 50:
                                                        st.markdown(f"  • **{key}**: *{len(value) if isinstance(value, list) else 'configured'}*")
                                                        with st.expander(f"View {key}", expanded=False):
                                                            st.json(value)
                                                    else:
                                                        st.markdown(f"  • **{key}**: `{value}`")
                                                st.markdown("---")
                                            
                                            # Display performance settings
                                            if performance_settings:
                                                st.markdown("**⚡ Performance & Limits:**")
                                                for key, value in performance_settings.items():
                                                    if isinstance(value, (list, dict)) and len(str(value)) > 50:
                                                        st.markdown(f"  • **{key}**: *{len(value) if isinstance(value, list) else 'configured'}*")
                                                        with st.expander(f"View {key}", expanded=False):
                                                            st.json(value)
                                                    else:
                                                        st.markdown(f"  • **{key}**: `{value}`")
                                                st.markdown("---")
                                            
                                            # Display other settings
                                            if other_settings:
                                                st.markdown("**🔧 Other Settings:**")
                                                for key, value in other_settings.items():
                                                    if isinstance(value, bool):
                                                        icon = "✅" if value else "❌"
                                                        st.markdown(f"  • **{key}**: {icon}")
                                                    elif isinstance(value, (list, dict)) and len(str(value)) > 50:
                                                        st.markdown(f"  • **{key}**: *{len(value) if isinstance(value, list) else 'configured'}*")
                                                        with st.expander(f"View {key}", expanded=False):
                                                            st.json(value)
                                                    else:
                                                        st.markdown(f"  • **{key}**: `{value}`")
                                            
                                            # Raw data expandable section for power users
                                            with st.expander("🔍 Raw Settings Data", expanded=False):
                                                st.json(advanced_settings)
                                        else:
                                            st.info("📋 No additional advanced settings configured")
                                            
                                except (json.JSONDecodeError, TypeError):
                                    st.error("❌ Failed to parse settings data")
                                    st.write(text_content)
                        else:
                            st.error(f"❌ Failed to get settings for {selected_index_name}")
                            st.error(result.get("error", "Unknown error"))
    
    else:
        st.info("👆 Click 'Load All Indices' to view your indices")
        st.markdown("**This will show you:**")
        st.markdown("- 📊 All indices in your application")
        st.markdown("- 📈 Record counts and sizes")  
        st.markdown("- ⚙️ Index settings and configuration")
        st.markdown("- 📅 Creation and update timestamps")
 
with tab3:
    st.subheader("🔍 Search Index")
    
    # Load index names if not available
    if not st.session_state.indices_names:
        col_load, col_refresh = st.columns([3, 1])
        with col_load:
            st.info("📋 Load your indices to see available options in the dropdown")
        with col_refresh:
            if st.button("📋 Load Indices", key="search_load_indices"):
                with st.spinner("Loading indices..."):
                    res = st.session_state.client.run_async(st.session_state.client.list_indices(app_id))
                    
                    if res.get("success"):
                        indices_raw = res.get("content", [])
                        indices_names = []
                        
                        for item in indices_raw:
                            text_content = getattr(item, "text", None) or str(item)
                            try:
                                indices_json = json.loads(text_content)
                                indices_list = indices_json.get("items", [])
                                for idx_item in indices_list:
                                    indices_names.append(idx_item.get("name", "Unknown"))
                            except (json.JSONDecodeError, TypeError, AttributeError):
                                continue
                        
                        st.session_state.indices_names = indices_names
                        st.toast(f"📋 Found {len(indices_names)} indices!", icon="📂")
                        st.rerun()
                    else:
                        st.error("❌ Failed to load indices")
                        st.error(res.get("error", "Unknown error"))
    
    # Search input fields
    col1, col2 = st.columns(2)
    with col1:
        # Index dropdown or text input fallback
        if st.session_state.indices_names:
            # Add refresh button next to dropdown
            col_dropdown, col_refresh = st.columns([4, 1])
            with col_dropdown:
                idx = st.selectbox(
                    "Select Index", 
                    options=st.session_state.indices_names,
                    key="search_idx",
                    help="Choose from your available indices"
                )
            with col_refresh:
                st.write("")  # Add spacing
                if st.button("🔄", key="refresh_indices", help="Refresh index list"):
                    with st.spinner("Refreshing..."):
                        res = st.session_state.client.run_async(st.session_state.client.list_indices(app_id))
                        if res.get("success"):
                            indices_raw = res.get("content", [])
                            indices_names = []
                            
                            for item in indices_raw:
                                text_content = getattr(item, "text", None) or str(item)
                                try:
                                    indices_json = json.loads(text_content)
                                    indices_list = indices_json.get("items", [])
                                    for idx_item in indices_list:
                                        indices_names.append(idx_item.get("name", "Unknown"))
                                except (json.JSONDecodeError, TypeError, AttributeError):
                                    continue
                            
                            st.session_state.indices_names = indices_names
                            st.toast(f"🔄 Refreshed! Found {len(indices_names)} indices", icon="✅")
                            st.rerun()
        else:
            # Fallback to text input if indices not loaded
            idx = st.text_input("Index name", key="search_idx_fallback", placeholder="e.g., products, customers, content")
        
        q = st.text_input("Query", key="search_q", placeholder="Enter your search terms...")
    with col2:
        hits = st.number_input(
            "📄 Results per page", 
            min_value=1, 
            max_value=1000, 
            value=20,
            help="How many search results to show on each page (1-1000)"
        )
        page = st.number_input(
            "📖 Page number", 
            min_value=0, 
            max_value=100000, 
            value=0,
            help="Which page of results to view (0 = first page, 1 = second page, etc.)"
        )
    
    # Search button
    if st.button("🔍 Search", type="primary", key="search_button"):
        if not idx:
            if st.session_state.indices_names:
                st.warning("⚠️ Please select an index from the dropdown")
            else:
                st.warning("⚠️ Please enter an index name or load your indices first")
        elif not q:
            st.warning("⚠️ Please enter a search query")
        else:
            # Add timing for search operation
            import time
            search_start_time = time.time()
            
            # Perform search
            search_result = st.session_state.client.run_async(
                st.session_state.client.search(app_id, idx, q, hits, page))
            
            # Calculate search time
            search_end_time = time.time()
            search_duration = search_end_time - search_start_time
            
            # Format time nicely
            if search_duration < 1:
                search_time_str = f"{search_duration*1000:.0f} milliseconds"
            else:
                search_time_str = f"{search_duration:.2f} seconds"
            
            # Show search results
            show_search_results(search_result)
            
            # Show toast notification with search time
            if search_result.get("success"):
                st.toast(f"🔍 Search completed in {search_time_str}!", icon="⚡")
    
    # Add helpful tips section
    with st.expander("💡 Search Tips & Examples", expanded=False):
        st.markdown("### 🎯 **What can you search for?**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**📝 Text & Content Searches:**")
            st.markdown("• `iPhone` - Find products containing 'iPhone'")
            st.markdown("• `john smith` - Search for names or multi-word terms")
            st.markdown("• `premium quality` - Find items with specific descriptions")
            st.markdown("• `2024` - Search by year or numbers")
            
            st.markdown("**🏷️ Category & Type Searches:**")
            st.markdown("• `electronics` - Find items by category")
            st.markdown("• `california` - Search by location")
            st.markdown("• `manager` - Find by job title or role")
            
        with col2:
            st.markdown("**🔤 Advanced Search Patterns:**")
            st.markdown("• `\"exact phrase\"` - Search for exact phrases")
            st.markdown("• `apple OR orange` - Find either term")
            st.markdown("• `laptop -gaming` - Exclude specific terms")
            st.markdown("• `price:>100` - Numeric filtering (if configured)")
            
            st.markdown("**📊 Common Use Cases:**")
            st.markdown("• Product names, SKUs, or descriptions")
            st.markdown("• Customer names, emails, or companies")
            st.markdown("• Article titles, content, or tags")
            st.markdown("• Locations, dates, or categories")
        
        st.markdown("---")
        st.markdown("**⚡ Pro Tips:**")
        st.markdown("• **Start simple**: Try single keywords first")
        st.markdown("• **Use quotes**: For exact phrase matching")
        st.markdown("• **Check spelling**: Algolia handles some typos but exact spelling works best")
        st.markdown("• **Try variations**: Different words for the same concept")
        st.markdown("• **Browse first**: Use the Indices tab to see what data is available")
        st.markdown("• **Look for highlights**: Matching terms will be <span style='background-color: #ffeb3b; color: #000; padding: 2px 4px; border-radius: 3px; font-weight: bold;'>highlighted</span> in yellow", unsafe_allow_html=True)
        
        st.info("💡 **Not sure what to search?** Go to the **Indices** tab first to see your available data and understand what fields are searchable.")
 
with tab6:
    # Import and call the upload functionality
    try:
        # Add mcp-node to path if not already there
        import sys
        import os
        
        mcp_node_path = os.path.join(os.path.dirname(__file__), 'mcp-node')
        if mcp_node_path not in sys.path:
            sys.path.insert(0, mcp_node_path)
        
        
        # Get the API key from environment
        admin_key = os.getenv("ALGOLIA_API_KEY")
        
        if admin_key:
            # Call the upload app with credentials
            algolia_upload_app(app_id, admin_key)
        else:
            st.error("❌ ALGOLIA_API_KEY not found in environment variables")
            
    except ImportError as e:
        st.error(f"❌ Failed to import upload functionality: {e}")
        st.info("Make sure algolia_uploader.py is in the mcp-node directory")
    except FileNotFoundError:
        st.error("❌ algolia_uploader.py not found in mcp-node directory")
        st.info("Please ensure the file exists at: ./mcp-node/algolia_uploader.py")
    except Exception as e:
        st.error(f"❌ Error loading upload tab: {e}")

with tab7:
    st.subheader("🤖 AI Chat Assistant")
    st.markdown("*Chat with your Algolia data using natural language powered by GPT-4*")
    
    # Initialize session state for chat
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "openai_messages" not in st.session_state:
        st.session_state.openai_messages = []
    
    # Check if OpenAI is available and properly configured
    if not OPENAI_AVAILABLE:
        st.error("❌ OpenAI package not installed")
        st.info("Install OpenAI: `pip install openai`")
        st.stop()
    
    # Check for Azure OpenAI credentials
    AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_API_BASE")
    AZURE_KEY = os.getenv("AZURE_OPENAI_API_KEY")
    AZURE_VER = "2025-02-01-preview"
    
    if not AZURE_ENDPOINT or not AZURE_KEY:
        st.error("❌ Azure OpenAI credentials not configured")
        st.markdown("""
        **Required environment variables:**
        - `AZURE_OPENAI_API_BASE` - Your Azure OpenAI endpoint
        - `AZURE_OPENAI_API_KEY` - Your Azure OpenAI API key
        
        Add these to your `.env` file to enable AI chat functionality.
        """)
        st.stop()
    
    # Check MCP connection
    if not st.session_state.connected:
        st.warning("🔌 Please connect to MCP Server in the sidebar first")
        st.stop()
    
    # Display chat history
    st.markdown("### 💬 Conversation")
    
    # Create a container for chat messages
    chat_container = st.container()
    with chat_container:
        for message in st.session_state.chat_history:
            display_chat_message(message)
    
    # Chat input section
    st.markdown("---")
    st.markdown("### ✍️ Ask me anything about your Algolia data!")
    
    # Chat input
    col1, col2 = st.columns([4, 1])
    with col1:
        query = st.text_input(
            "Your message:", 
            placeholder="e.g., 'Show me all my indices' or 'Search for products in my store'",
            key="chat_input"
        )
    with col2:
        st.write("")  # Add spacing
        send_button = st.button("💬 Send", type="primary", use_container_width=True)
    
    # Example buttons
    st.markdown("**💡 Quick Examples:**")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        example1 = st.button("📋 List my indices", key="example1")
    with col2:
        example2 = st.button("🔍 Search my data", key="example2")
    with col3:
        example3 = st.button("📊 Show analytics", key="example3")
    with col4:
        clear_chat = st.button("🗑️ Clear chat", key="clear_chat")
    
    # Handle example buttons
    if example1:
        query = "Show me all my Algolia indices with their record counts and sizes"
        send_button = True
    elif example2:
        query = f"Search for 'test' in the first available index in my {app} application"
        send_button = True
    elif example3:
        query = f"Show me analytics data for my {app} application indices"
        send_button = True
    elif clear_chat:
        st.session_state.chat_history = []
        st.session_state.openai_messages = []
        st.toast("🗑️ Chat cleared!", icon="✨")
        st.rerun()
    
    # Process user input
    if query and send_button:
        # Add user message to chat
        user_msg = ChatMessage(
            role="user",
            content=query,
            timestamp=get_timestamp()
        )
        st.session_state.chat_history.append(user_msg)
        
        # Check if we have MCP tools available
        if not st.session_state.client.tools:
            st.error("❌ No MCP tools available. Please reconnect to MCP server.")
            st.stop()
        
        # Build OpenAI tool specs
        oa_tools, name_map = [], {}
        for t in st.session_state.client.tools:
            try:
                oa_tools.append(to_openai_schema(t))
                name_map[t.name] = t
            except Exception as ex:
                st.warning(f"⚠️ Skipped tool {t.name}: {ex}")
        
        # Load system prompt
        try:
            with open("algolia_system_prompt.txt", encoding="utf-8") as f:
                system_prompt = f.read()
        except FileNotFoundError:
            system_prompt = fallback_prompt(app_id)
        
        # Initialize OpenAI messages if empty
        if not st.session_state.openai_messages:
            st.session_state.openai_messages = [{"role": "system", "content": system_prompt}]
        
        # Add user message to OpenAI messages
        st.session_state.openai_messages.append({"role": "user", "content": query})
        
        # Create OpenAI client
        client = AzureOpenAI(
            azure_endpoint=AZURE_ENDPOINT,
            api_key=AZURE_KEY,
            api_version=AZURE_VER,
        )
        
        with st.spinner("🤖 AI is thinking and calling tools..."):
            try:
                # Make initial request to GPT-4
                res = client.chat.completions.create(
                    model="gpt-4o",
                    messages=st.session_state.openai_messages,
                    tools=oa_tools,
                    tool_choice="auto",
                    temperature=0.1,
                )
                
                assistant_message_content = res.choices[0].message.content or ""
                tool_calls_made = []
                
                # Process tool calls if any
                if res.choices[0].message.tool_calls:
                    # Add assistant message with tool calls to OpenAI messages
                    st.session_state.openai_messages.append(res.choices[0].message)
                    preparer = ArgPreparer(app_id)
                    
                    for call in res.choices[0].message.tool_calls:
                        tname = call.function.name
                        try:
                            raw_args = json.loads(call.function.arguments or "{}")
                        except json.JSONDecodeError:
                            st.error(f"❌ {tname}: Invalid JSON arguments")
                            continue
                        
                        # Handle ALGOLIA_APP_ID conversion
                        if "ALGOLIA_APP_ID" in raw_args:
                            raw_args["applicationId"] = raw_args.pop("ALGOLIA_APP_ID")
                        
                        # Validate arguments
                        val = preparer.prepare(
                            getattr(name_map[tname], "inputSchema", {}) or {},
                            raw_args, tname)
                        
                        if not val.success:
                            error_msg = f"❌ {tname}: Missing required fields: {val.missing_fields}"
                            for e in val.errors:
                                error_msg += f"\n• {e}"
                            
                            tool_call_obj = ToolCall(
                                name=tname,
                                arguments=raw_args,
                                result={"error": error_msg},
                                success=False,
                                timestamp=get_timestamp()
                            )
                            tool_calls_made.append(tool_call_obj)
                            
                            # Add tool response to OpenAI messages
                            st.session_state.openai_messages.append({
                                "tool_call_id": call.id,
                                "role": "tool",
                                "name": tname,
                                "content": error_msg
                            })
                            continue
                        
                        # Show warnings if any
                        for w in val.warnings:
                            st.info(f"ℹ️ {w}")
                        
                        # Execute the tool
                        exec_res = st.session_state.client.run_async(
                            st.session_state.client.call_tool(tname, val.arguments))
                        
                        # Create tool call object
                        tool_call_obj = ToolCall(
                            name=tname,
                            arguments=val.arguments,
                            result=exec_res["content"] if exec_res["success"] else {"error": exec_res["error"]},
                            success=exec_res["success"],
                            timestamp=get_timestamp()
                        )
                        tool_calls_made.append(tool_call_obj)
                        
                        # Serialize and add to OpenAI messages  
                        serial_content = serialise(exec_res["content"]) if exec_res["success"] else {"error": exec_res["error"]}
                        st.session_state.openai_messages.append({
                            "tool_call_id": call.id,
                            "role": "tool",
                            "name": tname,
                            "content": json.dumps(serial_content)
                        })
                    
                    # Get final response from AI
                    final_response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=st.session_state.openai_messages,
                        temperature=0.3,
                    )
                    assistant_message_content = final_response.choices[0].message.content
                    
                    # Add final assistant message to OpenAI messages
                    st.session_state.openai_messages.append({
                        "role": "assistant", 
                        "content": assistant_message_content
                    })
                
                # Create assistant chat message
                assistant_msg = ChatMessage(
                    role="assistant",
                    content=assistant_message_content,
                    timestamp=get_timestamp(),
                    tool_calls=tool_calls_made if tool_calls_made else None
                )
                st.session_state.chat_history.append(assistant_msg)
                
            except Exception as e:
                st.error(f"❌ An error occurred: {str(e)}")
                error_msg = ChatMessage(
                    role="assistant",
                    content=f"I apologize, but I encountered an error: {str(e)}",
                    timestamp=get_timestamp()
                )
                st.session_state.chat_history.append(error_msg)
        
        # Clear input and rerun to show new messages
        st.rerun()
    
    # Show helpful information when chat is empty
    if not st.session_state.chat_history:
        st.markdown("---")
        st.markdown("### 🌟 What can you ask me?")
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("""
            **📊 Data Management:**
            - "Show me all my indices"
            - "How many records are in my products index?"
            - "Add a new record to my database"
            - "Update a specific record"
            
            **🔍 Search & Discovery:**
            - "Search for 'iPhone' in my products"
            - "Find all records with missing descriptions"
            - "Show me the most relevant results for 'laptop'"
            """)
        
        with col2:
            st.markdown("""
            **📈 Analytics & Insights:**
            - "What are my most popular searches?"
            - "Show me search analytics for last month"
            - "Which queries return no results?"
            - "How is my search performance?"
            
            **⚙️ Configuration:**
            - "Show me my index settings"
            - "List all my search synonyms"
            - "What are my ranking rules?"
            """)
        
        st.info("💡 **Tip:** Just ask in natural language! I'll figure out which tools to use and help you get the answers you need.")


# ──────────────────────────────────
# tidy shutdown
# ──────────────────────────────────
def _cleanup():
    try:
        if "client" in st.session_state and st.session_state.client:
            st.session_state.client.run_async(
                st.session_state.client.disconnect())
    except Exception:
        pass
atexit.register(_cleanup)
