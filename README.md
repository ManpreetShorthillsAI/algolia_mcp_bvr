# 🔍 Algolia MCP (Model Context Protocol) Project

<p align="center">
  <strong>Natural Language Interface for Algolia Search & Analytics</strong>
</p>

<p align="center">
  <a href="#-overview">Overview</a> •
  <a href="#-features">Features</a> •
  <a href="#-project-structure">Project Structure</a> •
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-installation">Installation</a> •
  <a href="#-usage">Usage</a> •
  <a href="#-configuration">Configuration</a> •
  <a href="#-development">Development</a> •
  <a href="#-troubleshooting">Troubleshooting</a>
</p>

---

## 🎯 Overview

This project provides a comprehensive interface for interacting with Algolia's search and analytics platform through natural language. It combines the **official Algolia MCP Server** with a **custom Python Streamlit Web Application** to enable seamless integration with Claude Desktop and other AI assistants.

> **⚠️ Experimental Project**: This is an experimental implementation for exploring and experimenting with Algolia APIs through MCP. The MCP Node.js server component is based on [Algolia's official implementation](https://github.com/algolia/mcp-node), while the Streamlit interface is custom-built for enhanced usability.

## ✨ Features

### 🤖 Natural Language Interactions
- Search and manipulate indices with conversational prompts
- AI-powered data analysis and insights
- Automated chart and graph generation
- Intelligent query optimization

### 🔧 Comprehensive Algolia Operations
- **Index Management**: Create, configure, and manage search indices
- **Data Operations**: Add, update, delete, and batch process records
- **Search & Analytics**: Advanced search with filtering, faceting, and analytics
- **Monitoring**: Application status, performance metrics, and incident tracking
- **A/B Testing**: Manage and analyze search experiments

### 🖥️ Multiple Interfaces
- **Claude Desktop Integration**: Direct MCP server connection
- **Streamlit Web UI**: User-friendly web interface with chat functionality
- **Python API**: Direct programmatic access for custom integrations

## 📁 Project Structure

```
algolia_mcp_bvr_test/
├── 📂 mcp-node/                    # Official Algolia MCP Server (forked subrepo)
│   ├── src/                        # TypeScript source code
│   ├── package.json                # Node.js dependencies
│   └── README.md                   # Detailed MCP server documentation
├── 📄 streamlit_app.py             # Custom Streamlit web application (90KB)
├── 📄 algolia_uploader.py          # Custom data upload utilities (26KB)
├── 📄 algolia_system_prompt.txt    # AI assistant configuration (14KB)
├── 📄 .gitignore                   # Git ignore patterns
└── 📄 README.md                    # This file
```

### Component Details

- **🔗 Official MCP Server** (`mcp-node/`): Forked from [Algolia's official MCP Node.js repository](https://github.com/algolia/mcp-node) - provides 60+ authenticated Algolia API tools with MIT license
- **🌐 Custom Streamlit App** (`streamlit_app.py`): Web UI with chat interface and data visualization
- **⬆️ Custom Data Uploader** (`algolia_uploader.py`): Bulk data upload with size optimization and error handling
- **🤖 System Prompt** (`algolia_system_prompt.txt`): Pre-configured AI assistant for Algolia operations

### About the MCP Node.js Server

The `mcp-node/` directory contains a forked subrepo of [**Algolia's official MCP implementation**](https://github.com/algolia/mcp-node). This is significant because:

- **🏢 Official Algolia Support**: Built and maintained by the Algolia team (66+ stars, active development)
- **🔐 Production-Ready Authentication**: Secure authentication flow with Algolia Dashboard integration
- **🛠️ Comprehensive API Coverage**: Complete access to Algolia's Search, Analytics, Monitoring, and Management APIs
- **📈 Active Development**: Regular updates and improvements from the official Algolia team
- **🔄 Upstream Sync**: Can be updated with latest features from the official repository

> **Note**: While the MCP server is based on Algolia's official work, this overall project combines it with custom tools for enhanced functionality and ease of use.

## 🚀 Quick Start

### Option 1: Streamlit Web Interface

```bash
# 1. Install Python dependencies
pip install streamlit pandas requests python-dotenv nest-asyncio openai

# 2. Set up environment variables
echo "ALGOLIA_APPLICATION_ID=your_app_id" > .env
echo "ALGOLIA_API_KEY=your_api_key" >> .env

# 3. Start the web application
streamlit run streamlit_app.py
```

### Option 2: Claude Desktop Integration

```bash
# 1. Build the MCP server
cd mcp-node
npm install
npm run build

# 2. Configure Claude Desktop (see Configuration section)
# 3. Start using natural language prompts in Claude Desktop
```

## 📦 Installation

### Prerequisites

- **Node.js**: ≥22.0.0
- **Python**: ≥3.8
- **Algolia Account**: Valid Application ID and API Key

### Python Environment Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install streamlit pandas requests python-dotenv nest-asyncio

# Optional: For AI chat functionality
pip install openai
```

### Node.js Environment Setup

```bash
cd mcp-node
npm install
npm run type-check  # Verify TypeScript compilation
npm run lint        # Check code quality
```

## 🎮 Usage

### Streamlit Web Interface

1. **Launch the app**: `streamlit run streamlit_app.py`
2. **Configure credentials** in the sidebar
3. **Choose your workflow**:
   - **Chat Assistant**: Natural language interactions
   - **Data Uploader**: Bulk data import
   - **Direct API**: Raw tool execution

### Natural Language Examples

```
"List all my applications and their indices"
"Search for 'wireless headphones' in my products index"
"Show me the top searches with no results this week"
"Add these 10 products to my inventory index"
"What's the current performance of my search analytics?"
"Generate a chart showing daily search volumes"
```

### Claude Desktop Integration

After configuring Claude Desktop, you can use prompts like:

```
"What indices are in my e-commerce application?"
"Search for Nike shoes under $100 in my products index"
"Show me analytics for the past month with a visualization"
```

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the root directory:

```env
# Required
ALGOLIA_APPLICATION_ID=your_application_id
ALGOLIA_API_KEY=your_api_key

# Optional - for AI chat functionality
AZURE_OPENAI_ENDPOINT=your_azure_endpoint
AZURE_OPENAI_API_KEY=your_azure_key
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_OPENAI_DEPLOYMENT_NAME=your_deployment_name
```

### Claude Desktop Configuration

Add to your Claude Desktop configuration file:

```json
{
  "mcpServers": {
    "algolia": {
      "command": "node",
      "args": ["--experimental-strip-types", "--no-warnings=ExperimentalWarnings", "/path/to/mcp-node/src/app.ts"],
      "env": {
        "ALGOLIA_APPLICATION_ID": "your_app_id",
        "ALGOLIA_API_KEY": "your_api_key"
      }
    }
  }
}
```

## 🛠️ Development

### Running in Development Mode

```bash
# Start Streamlit with auto-reload
streamlit run streamlit_app.py --server.runOnSave true

# Start MCP server with debugging
cd mcp-node
npm run debug

# Type checking
npm run type-check
```

### Project Scripts

```bash
# Node.js MCP Server
npm start          # Start production server
npm run debug      # Start with MCP inspector
npm run build      # Compile to executable
npm test           # Run test suite

# Python Application
python streamlit_app.py              # Direct execution
streamlit run streamlit_app.py       # Streamlit server
python algolia_uploader.py           # Direct uploader usage
```

### Testing

```bash
cd mcp-node
npm test           # Run Vitest test suite
npm run test:coverage  # Generate coverage report
```

## 🐛 Troubleshooting

### Common Issues

**1. "Module not found" errors**
```bash
# Ensure all dependencies are installed
pip install -r requirements.txt  # If you create one
cd mcp-node && npm install
```

**2. Authentication failures**
```bash
# Verify your Algolia credentials
echo $ALGOLIA_APPLICATION_ID
echo $ALGOLIA_API_KEY
```

**3. Streamlit connection issues**
```bash
# Check if ports are available
lsof -i :8501  # Default Streamlit port
```

**4. MCP server not connecting**
```bash
# Test the server directly
cd mcp-node
npm run debug
```

### Debug Mode

Enable debug logging in the Streamlit app by adding:
```python
st.set_page_config(page_title="Algolia MCP", layout="wide")
st.sidebar.checkbox("Debug Mode", key="debug_mode")
```

## 📚 Additional Resources

- **[Algolia's Official MCP Node.js Repository](https://github.com/algolia/mcp-node)** - Upstream repository for the MCP server component
- **[Algolia Documentation](https://www.algolia.com/doc/)**
- **[Model Context Protocol Specification](https://spec.modelcontextprotocol.io)**
- **[Streamlit Documentation](https://docs.streamlit.io)**
- **[Node.js MCP Server Details](./mcp-node/README.md)**

## 🤝 Contributing

This project has two main components with different contribution workflows:

### MCP Server Contributions
For improvements to the MCP Node.js server (`mcp-node/`), please contribute directly to [**Algolia's official repository**](https://github.com/algolia/mcp-node). This ensures your contributions benefit the entire community and get proper review from the Algolia team.

### Custom Components Contributions
For the Streamlit web interface, data uploader, or project configuration:
- Fork this repository
- Submit issues and feature requests  
- Contribute improvements via pull requests

> **Note**: This project is provided "as is" for experimentation. The MCP server component is maintained by Algolia, while the custom components are community-driven.

## ⚖️ License

This project is provided under the ISC License. See the [LICENSE](./mcp-node/LICENSE) file for details.

---

<p align="center">
  <strong>🔍 Happy Searching with Algolia MCP! 🔍</strong>
</p>
