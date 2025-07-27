# 🔍 Algolia MCP - Natural Language Search Interface

<p align="center">
  <strong>Advanced Natural Language Interface for Algolia Search & Analytics</strong>
</p>

<p align="center">
  <a href="#-overview">Overview</a> •
  <a href="#-features">Features</a> •
  <a href="#-project-structure">Project Structure</a> •
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-installation">Installation</a> •
  <a href="#-usage-guide">Usage Guide</a> •
  <a href="#-development">Development</a> •
  <a href="#-api-reference">API Reference</a>
</p>

---

## 🎯 Overview

**Algolia MCP**  is a sophisticated interface that combines Algolia's powerful search capabilities with natural language processing and AI-driven interactions. This project integrates the official Algolia MCP (Model Context Protocol) server with custom Python applications to provide seamless search experiences through conversational interfaces.

### Key Innovation
This implementation goes beyond basic search by incorporating behavioral analytics and vector representations, enabling more intelligent and context-aware search interactions.

> **🔗 Built on Official Foundation**: Uses [Algolia's official MCP Node.js server](https://github.com/algolia/mcp-node) as the core API interface, enhanced with custom behavioral analysis and UI components.

## ✨ Features

### 🧠 Intelligent Search Capabilities
- **Natural Language Queries**: Convert conversational prompts into optimized Algolia searches
- **Behavioral Analysis**: Track and analyze search patterns for improved relevance
- **Vector-Based Matching**: Enhanced search results through semantic understanding
- **Context-Aware Results**: Maintain conversation context across multiple queries

### 🔧 Comprehensive Algolia Integration
- **Full API Coverage**: Complete access to Search, Analytics, Monitoring, and Management APIs
- **Real-time Analytics**: Live performance metrics and user behavior insights
- **Index Management**: Create, configure, and optimize search indices
- **A/B Testing**: Manage and analyze search experiments
- **Bulk Operations**: Efficient batch processing for large datasets

### 🖥️ Multi-Interface Architecture
- **Web Application**: Rich web interface with interactive visualizations
- **Claude Desktop Integration**: Direct MCP protocol connection for AI assistants
- **Python API**: Programmatic access for custom integrations
- **Chat Assistant**: AI-powered conversational search interface

## 📁 Project Structure

```
algolia_mcp_bvr/
├── 📄 streamlit_app.py             # Main Streamlit web application (90KB)
│   ├── 🤖 AI Chat Assistant        # Natural language search interface
│   ├── 📊 Analytics Dashboard      # Search performance metrics
│   ├── 🔧 Direct API Tools         # Raw Algolia API access
│   └── 📈 Data Visualization       # Interactive charts and graphs
│
├── 📄 algolia_uploader.py          # Advanced data processing utilities (26KB)
│   ├── 🔄 Bulk Data Import         # Efficient batch uploads
│   ├── 📏 Size Optimization        # Record size management
│   ├── 🧹 Data Cleaning            # JSON validation and sanitization
│   └── ⚡ Performance Monitoring   # Upload progress and error handling
│
├── 📄 algolia_system_prompt.txt    # AI assistant configuration (14KB)
│   ├── 🎯 Behavior Guidelines      # AI interaction rules
│   ├── 🔍 Search Optimization     # Query enhancement strategies
│   ├── 📚 Tool Documentation       # Available API functions
│   └── 🤝 User Experience Rules    # Conversation flow management
│
├── 📂 mcp-node/                    # Official Algolia MCP Server
│   └── 🔗 [Integration Point]      # Will contain forked official server
│
├── 📄 .gitignore                   # Git exclusion patterns
└── 📄 README.md                    
```

## 🚀 Quick Start

### Option 1: Streamlit Web Interface (Recommended)

```bash
# 1. Clone and navigate to project
cd algolia_mcp_bvr

# 2. Install Python dependencies
pip install streamlit pandas requests python-dotenv nest-asyncio

# 3. Optional: Install AI chat functionality
pip install openai  # For Azure OpenAI integration

# 4. Configure environment
echo "ALGOLIA_APPLICATION_ID=your_app_id" > .env
echo "ALGOLIA_API_KEY=your_api_key" >> .env

# 5. Launch the application
streamlit run streamlit_app.py
```

### Option 2: Claude Desktop Integration

```bash
# 1. Set up MCP server (when available)
cd mcp-node
npm install && npm run build

# 2. Configure Claude Desktop
# Add MCP server configuration to Claude settings

# 3. Start natural language interactions
```

## 📦 Installation

### Prerequisites
- **Python**: ≥3.8 (recommend 3.9+)
- **Node.js**: ≥22.0.0 (for MCP server)
- **Algolia Account**: Valid Application ID and API Key

### Detailed Setup

#### Python Environment
```bash
# Create isolated environment
python -m venv algolia_env
source algolia_env/bin/activate  # Windows: algolia_env\Scripts\activate

# Core dependencies
pip install streamlit pandas requests python-dotenv nest-asyncio

# Optional AI features
pip install openai azure-openai

# Development tools (optional)
pip install black flake8 pytest
```

#### Environment Configuration
```bash
# Create .env file with your credentials
cat > .env << EOF
# Required Algolia credentials
ALGOLIA_APPLICATION_ID=your_application_id
ALGOLIA_API_KEY=your_admin_api_key

# Optional AI chat configuration
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your_azure_key
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_OPENAI_DEPLOYMENT_NAME=your_deployment_name
```

## 🎮 Usage Guide

### Streamlit Web Application

1. **Launch**: `streamlit run streamlit_app.py`
2. **Access**: Open http://localhost:8501 in your browser
3. **Configure**: Enter Algolia credentials in the sidebar
4. **Choose Mode**:
   - **🤖 AI Chat**: Natural language search interactions
   - **📊 Analytics**: Performance metrics and insights  
   - **🔧 Direct API**: Raw tool execution
   - **📈 Upload**: Bulk data import with optimization

### Natural Language Examples

#### Search Operations
```
"Find all products with 'wireless' in the name from my electronics index"
"Show me search analytics for the past 7 days"
"What are the top 10 queries with no results?"
"Add these 50 products to my inventory index with automatic ID generation"
```

#### Analytics & Insights
```
"Generate a chart showing daily search volume trends"
"What's the click-through rate for my product searches?"
"Show me the performance comparison between different indices"
"Create a visualization of search patterns by region"
```

#### Index Management
```
"List all indices in my application with their record counts"
"Configure faceting for category and brand attributes"
"Set up custom ranking for my products index"
"Show me the current index settings and synonyms"
```

### Data Upload Features

The `algolia_uploader.py` provides advanced capabilities:

- **📏 Smart Size Management**: Automatically truncates large fields to stay under Algolia's limits
- **🧹 Data Validation**: Cleans JSON-incompatible values and validates records
- **⚡ Batch Processing**: Efficient bulk uploads with progress tracking
- **🔄 Error Recovery**: Robust error handling with retry mechanisms
- **📊 Upload Analytics**: Detailed statistics and performance metrics


## 🛠️ Development

### Running in Development Mode

```bash
# Start with auto-reload and debugging
streamlit run streamlit_app.py --server.runOnSave true --server.port 8501

# Enable debug logging
export DEBUG_MODE=true
streamlit run streamlit_app.py
```

### Code Structure

#### Main Application (`streamlit_app.py`)
- **Session Management**: MCP client lifecycle management
- **UI Components**: Modular interface components
- **Tool Integration**: Algolia API tool wrapper functions
- **Chat System**: AI conversation management
- **Data Visualization**: Chart and graph generation

#### Data Utilities (`algolia_uploader.py`)
- **Record Processing**: Size optimization and validation
- **Batch Operations**: Efficient bulk upload handling
- **Error Management**: Comprehensive error handling
- **Progress Tracking**: Real-time upload monitoring

### Testing

```bash
# Test individual components
python -c "from algolia_uploader import check_record_size; print('Import successful')"

# Test Streamlit app
streamlit run streamlit_app.py --server.headless true
```

### Debugging

Enable debug mode by setting environment variable:
```bash
export DEBUG_MODE=true
```

This will provide:
- Detailed API call logging
- Request/response inspection
- Performance timing information
- Error stack traces

## 📊 API Reference

### Core Functions

#### Search Operations
- `searchSingleIndex()`: Execute searches with filters and facets
- `getTopSearches()`: Retrieve popular search queries
- `getNoResultsRate()`: Analyze search effectiveness

#### Index Management
- `listIndices()`: Get all indices with metadata
- `getSettings()`: Retrieve index configuration
- `setAttributesForFaceting()`: Configure faceting attributes

#### Data Operations
- `saveObject()`: Add new records
- `partialUpdateObject()`: Update existing records
- `batch()`: Bulk operations

#### Analytics
- `getTopHits()`: Most clicked search results
- `getMetrics()`: Performance analytics
- `getIncidents()`: Service status monitoring


## 🐛 Troubleshooting

### Common Issues

#### 1. Authentication Errors
```bash
# Verify credentials
python -c "import os; print(f'App ID: {os.getenv(\"ALGOLIA_APPLICATION_ID\")}[:8]}...')"

# Test connection
streamlit run streamlit_app.py --server.headless true
```

#### 2. Import/Module Errors
```bash
# Check Python environment
pip list | grep -E "(streamlit|pandas|requests)"
python --version
```

#### 3. Upload Size Issues
```bash
# Check record sizes
python -c "from algolia_uploader import check_record_size; print('Size checker ready')"
```

#### 4. MCP Connection Issues
```bash
# Verify Node.js environment (when MCP server is set up)
node --version  # Should be ≥22.0.0
```

### Debug Tools

#### Enable Detailed Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

#### Monitor API Calls
Set `DEBUG_MODE=true` to see all API interactions in the Streamlit interface.

## 📚 Resources

### Official Documentation
- **[Algolia's Official MCP Repository](https://github.com/algolia/mcp-node)** - Upstream MCP server
- **[Algolia API Documentation](https://www.algolia.com/doc/api-reference/)** - Complete API reference
- **[Model Context Protocol](https://spec.modelcontextprotocol.io)** - MCP specification

### Development Resources
- **[Streamlit Documentation](https://docs.streamlit.io)** - Web framework reference
- **[Python Environment Management](https://docs.python.org/3/tutorial/venv.html)** - Virtual environments

### Community
- **[Algolia Community Forum](https://discourse.algolia.com/)** - Get help and share ideas
- **[MCP Developers](https://github.com/modelcontextprotocol)** - Protocol development

## 🤝 Contributing

### Project Components

#### Core Application (`streamlit_app.py`, `algolia_uploader.py`)
- Fork this repository
- Create feature branches for improvements
- Submit pull requests with detailed descriptions
- Follow Python PEP 8 style guidelines

#### MCP Server Integration
- For MCP server improvements, contribute to [Algolia's official repository](https://github.com/algolia/mcp-node)
- Sync updates from upstream when available
- Report integration issues in this repository

### Development Workflow

1. **Fork and Clone**
   ```bash
   git clone your-fork-url
   cd algolia_mcp_bvr
   ```

2. **Create Environment**
   ```bash
   python -m venv dev_env
   source dev_env/bin/activate
   pip install -r requirements.txt  # if created
   ```

3. **Make Changes**
   - Follow existing code patterns
   - Add comments for complex logic
   - Test thoroughly with different data types

4. **Submit Pull Request**
   - Clear description of changes
   - Include examples of new functionality
   - Update documentation if needed


## 🎉 Acknowledgments

- **Algolia Team**: For the excellent official MCP server implementation
- **Streamlit Community**: For the powerful web framework
- **Python Ecosystem**: For robust data processing libraries

---

<p align="center">
  <strong>🔍 Empowering Search with Intelligence - Algolia MCP 🔍</strong>
</p>