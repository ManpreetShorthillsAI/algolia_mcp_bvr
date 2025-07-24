import streamlit as st
import pandas as pd
import json
import uuid
import requests
import time
from typing import Dict, Any, List, Tuple

def check_record_size(record: Dict[str, Any]) -> int:
    """Check the size of a record in bytes"""
    try:
        if not isinstance(record, dict):
            st.error(f"check_record_size: Expected dict, got {type(record)}: {record}")
            return 0
        
        # Clean the record before JSON serialization to avoid JSON compliance errors
        cleaned_record = clean_json_incompatible_values(record)
        return len(json.dumps(cleaned_record, ensure_ascii=False).encode('utf-8'))
    except ValueError as e:
        if "Out of range float values are not JSON compliant" in str(e):
            st.warning(f"Found JSON-incompatible float values in record. Attempting to clean...")
            try:
                cleaned_record = clean_json_incompatible_values(record)
                return len(json.dumps(cleaned_record, ensure_ascii=False).encode('utf-8'))
            except Exception as clean_e:
                st.error(f"Error cleaning record for size check: {clean_e}")
                return 0
        else:
            st.error(f"JSON serialization error in record size check: {e}")
            return 0
    except Exception as e:
        st.error(f"Error checking record size: {e}")
        return 0

def truncate_large_fields(record: Dict[str, Any], max_size: int = 9000) -> Dict[str, Any]:
    """Truncate large text fields to keep record under size limit"""
    # Ensure we're working with a dictionary
    if not isinstance(record, dict):
        st.error(f"Expected dictionary, got {type(record)}")
        return record
        
    record_copy = record.copy()
    current_size = check_record_size(record_copy)
    
    if current_size <= max_size:
        return record_copy
    
    # Find text fields that might be large
    text_fields = []
    try:
        for key, value in record_copy.items():
            if isinstance(value, str) and len(value) > 100:
                text_fields.append((key, len(value)))
    except Exception as e:
        st.error(f"Error processing record fields: {e}")
        return record_copy
    
    # Sort by length (largest first)
    text_fields.sort(key=lambda x: x[1], reverse=True)
    
    # Truncate fields until record is small enough
    for field_name, field_length in text_fields:
        if current_size <= max_size:
            break
            
        try:
            # Calculate how much to truncate
            excess = current_size - max_size
            new_length = max(100, field_length - excess - 100)  # Leave some buffer
            
            # Truncate the field
            original_value = record_copy[field_name]
            if isinstance(original_value, str):
                record_copy[field_name] = original_value[:new_length] + "..."
            
            current_size = check_record_size(record_copy)
        except Exception as e:
            st.warning(f"Error truncating field {field_name}: {e}")
            continue
    
    return record_copy

def validate_and_fix_records(records: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], bool]:
    """Validate record sizes and check for records that are too large"""
    if not isinstance(records, list):
        st.error(f"Expected list of records, got {type(records)}")
        return [], False
        
    fixed_records = []
    large_records_info = []
    has_oversized_records = False
    
    for i, record in enumerate(records):
        try:
            if not isinstance(record, dict):
                st.warning(f"Record {i+1} is not a dictionary (got {type(record)}). Skipping.")
                continue
            
            # Clean JSON-incompatible values as an extra safety measure
            record = clean_json_incompatible_values(record)
                
            record_size = check_record_size(record)
            
            if record_size > 10000:  # Algolia's limit
                has_oversized_records = True
                large_records_info.append(f"Record {i+1}: {record_size} bytes")
                # COMMENTED OUT: Truncation functionality
                # st.warning(f"Record {i+1} is {record_size} bytes (too large). Truncating large fields...")
                # fixed_record = truncate_large_fields(record)
                # fixed_records.append(fixed_record)
                continue  # Skip this record entirely
            else:
                fixed_records.append(record)
        except Exception as e:
            st.error(f"Error processing record {i+1}: {e}")
            # Try to include the record anyway after cleaning
            try:
                cleaned_record = clean_json_incompatible_values(record)
                record_size = check_record_size(cleaned_record)
                if record_size <= 10000:
                    fixed_records.append(cleaned_record)
                else:
                    has_oversized_records = True
                    large_records_info.append(f"Record {i+1}: {record_size} bytes (after cleaning)")
            except Exception:
                st.warning(f"Skipping record {i+1} due to unrecoverable errors")
                continue
    
    # Show error if there are oversized records
    if has_oversized_records:
        st.error("🚫 **Algolia Per-Record Limit Exceeded - Cannot Upload**")
        st.error("**Algolia has a 10KB limit per record. The following records exceed this limit:**")
        for info in large_records_info:
            st.error(f"• {info}")
        st.error("**Please reduce the size of these records and try again.**")
        st.info("💡 **Suggestions:**")
        st.info("• Shorten long text fields")
        st.info("• Remove unnecessary data")
        st.info("• Split large records into multiple smaller records")
        return [], False
    
    return fixed_records, True

def get_index_stats(app_id: str, admin_key: str, index_name: str) -> int:
    """Get number of records in an Algolia index using search API"""
    try:
        # Use search endpoint with empty query to get total record count
        url = f"https://{app_id}-dsn.algolia.net/1/indexes/{index_name}/query"
        headers = {
            "X-Algolia-API-Key": admin_key,
            "X-Algolia-Application-Id": app_id,
            "Content-Type": "application/json"
        }
        # Search with empty query and no results to just get the count
        search_data = {"query": "", "hitsPerPage": 0}
        response = requests.post(url, headers=headers, json=search_data, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return data.get('nbHits', 0)
        elif response.status_code == 404:
            return -1  # Index doesn't exist
        else:
            st.error(f"❌ Error getting index stats: HTTP {response.status_code}")
            return 0
    except Exception as e:
        st.error(f"❌ Error getting index stats: {str(e)}")
        return 0

def process_file(uploaded_file) -> List[Dict[str, Any]]:
    """Process uploaded JSON or CSV file and return list of records"""
    try:
        if uploaded_file.type == "application/json" or uploaded_file.name.endswith('.json'):
            # Process JSON file
            content = uploaded_file.read().decode('utf-8')
            data = json.loads(content)
            
            if isinstance(data, list):
                records = data
            elif isinstance(data, dict):
                records = [data]
            else:
                st.error("JSON file must contain an object or array of objects")
                return []
            
        elif uploaded_file.type == "text/csv" or uploaded_file.name.endswith('.csv'):
            # Process CSV file
            try:
                df = pd.read_csv(uploaded_file)
                records = df.to_dict('records')
                
                # Clean JSON-incompatible values from CSV data
                st.info("🧹 Cleaning CSV data for JSON compatibility...")
                cleaned_records = []
                for record in records:
                    cleaned_record = clean_json_incompatible_values(record)
                    cleaned_records.append(cleaned_record)
                records = cleaned_records
                st.success(f"✅ CSV data cleaned successfully!")
                
            except Exception as e:
                st.error(f"Error reading CSV file: {str(e)}")
                return []
        else:
            st.error("Unsupported file type. Please upload JSON or CSV files only.")
            return []
        
        # Add objectID to each record if not present
        for record in records:
            if 'objectID' not in record:
                record['objectID'] = str(uuid.uuid4())
        
        return records
        
    except Exception as e:
        st.error(f"Error processing file: {str(e)}")
        return []

def clean_json_incompatible_values(record: Dict[str, Any]) -> Dict[str, Any]:
    """Clean record of JSON-incompatible float values (NaN, inf, -inf)"""
    import math
    
    if not isinstance(record, dict):
        return record
    
    cleaned_record = {}
    for key, value in record.items():
        if isinstance(value, float):
            if math.isnan(value):
                cleaned_record[key] = None  # Convert NaN to null
            elif math.isinf(value):
                if value > 0:
                    cleaned_record[key] = "Infinity"  # Convert +inf to string
                else:
                    cleaned_record[key] = "-Infinity"  # Convert -inf to string
            else:
                cleaned_record[key] = value
        elif isinstance(value, dict):
            cleaned_record[key] = clean_json_incompatible_values(value)
        elif isinstance(value, list):
            cleaned_record[key] = [clean_json_incompatible_values(item) if isinstance(item, dict) else 
                                 (None if isinstance(item, float) and math.isnan(item) else
                                  "Infinity" if isinstance(item, float) and math.isinf(item) and item > 0 else
                                  "-Infinity" if isinstance(item, float) and math.isinf(item) and item < 0 else item)
                                 for item in value]
        else:
            cleaned_record[key] = value
    
    return cleaned_record

def upload_to_algolia(app_id: str, admin_key: str, index_name: str, records: List[Dict[str, Any]], batch_size: int = 1000, replace_index: bool = False) -> bool:
    """Upload records to Algolia index using REST API"""
    try:
        # Start timing the upload
        start_time = time.time()
        if replace_index:
            # Clear the index first
            clear_url = f"https://{app_id}-dsn.algolia.net/1/indexes/{index_name}/clear"
            headers = {
                "X-Algolia-API-Key": admin_key,
                "X-Algolia-Application-Id": app_id,
                "Content-Type": "application/json"
            }
            clear_response = requests.post(clear_url, headers=headers, timeout=30)
            if clear_response.status_code not in [200, 201]:
                st.error(f"Failed to clear index: {clear_response.status_code}")
                return False
            
            st.info("✅ Index cleared successfully")
            time.sleep(2)  # Wait for clearing to complete
        
        # Upload in batches
        total_records = len(records)
        total_batches = (total_records + batch_size - 1) // batch_size
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        url = f"https://{app_id}-dsn.algolia.net/1/indexes/{index_name}/batch"
        headers = {
            "X-Algolia-API-Key": admin_key,
            "X-Algolia-Application-Id": app_id,
            "Content-Type": "application/json"
        }
        
        for i in range(0, total_records, batch_size):
            batch = records[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            
            status_text.text(f"Uploading batch {batch_num}/{total_batches} ({len(batch)} records)...")
            
            # Prepare batch request
            batch_requests = []
            for record in batch:
                batch_requests.append({
                    "action": "addObject",
                    "body": record
                })
            
            payload = {"requests": batch_requests}
            
            # Upload batch
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            
            if response.status_code not in [200, 201]:
                st.error(f"Batch {batch_num} failed: {response.status_code} - {response.text}")
                return False
            
            # Update progress
            progress = min(1.0, (i + len(batch)) / total_records)
            progress_bar.progress(progress)
            
            # Small delay between batches
            if batch_num < total_batches:
                time.sleep(0.5)
        
        # Calculate upload time
        end_time = time.time()
        upload_duration = end_time - start_time
        
        # Format time nicely
        if upload_duration < 60:
            time_str = f"{upload_duration:.1f} seconds"
        else:
            minutes = int(upload_duration // 60)
            seconds = upload_duration % 60
            time_str = f"{minutes}m {seconds:.1f}s"
        
        status_text.text(f"✅ Upload completed in {time_str}!")
        progress_bar.progress(1.0)
        
        # Store timing info in session state for popup display
        st.session_state.upload_time_text = time_str
        
        return True
        
    except Exception as e:
        st.error(f"Upload failed: {str(e)}")
        return False

def get_existing_indices(app_id: str, admin_key: str):
    """Display existing indices"""
    st.subheader("📋 Your Existing Indices")
    
    with st.expander("👀 View Your Current Indices", expanded=False):
        try:
            url = f"https://{app_id}-dsn.algolia.net/1/indexes"
            headers = {
                "X-Algolia-API-Key": admin_key,
                "X-Algolia-Application-Id": app_id,
                "Content-Type": "application/json"
            }
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                indices = data.get('items', [])
                
                st.success(f"✅ Successfully retrieved {len(indices)} indices")
                
                if indices:
                    st.write(f"**Found {len(indices)} indices in your account:**")
                    
                    # Create a nice table display
                    indices_data = []
                    for idx in indices:
                        name = idx.get('name', 'N/A')
                        entries = idx.get('entries', 0)
                        created = idx.get('createdAt', 'N/A')
                        updated = idx.get('updatedAt', 'N/A')
                        
                        indices_data.append({
                            "Index Name": name,
                            "Records": f"{entries:,}",
                            "Created": created,
                            "Updated": updated
                        })
                    
                    # Display as dataframe
                    if indices_data:
                        df = pd.DataFrame(indices_data)
                        st.dataframe(df, use_container_width=True)
                else:
                    st.info("No indices found in your account")
            else:
                st.error(f"Failed to retrieve indices: {response.status_code}")
                
        except Exception as e:
            st.error(f"Error retrieving indices: {str(e)}")

def algolia_upload_app(app_id: str, admin_key: str):
    """Main upload application function that accepts credentials from parent app"""
    
    # Initialize session state for upload time tracking
    if 'upload_time_text' not in st.session_state:
        st.session_state.upload_time_text = ""
    
    # Simple header without heavy styling
    st.subheader("📤 Algolia File Uploader")
    st.markdown("Upload JSON or CSV files directly to your Algolia indices")
    
    # Create two main columns using most of the screen width
    left_col, right_col = st.columns([4, 3], gap="large")
    
    with left_col:
        # Get existing indices
        get_existing_indices(app_id, admin_key)
        
        # Index Name Input
        st.subheader("📝 Index Name")
        col1, col2 = st.columns([3, 1])
        
        with col1:
            index_name = st.text_input(
                "Enter index name", 
                placeholder="e.g., my_products, customer_data, sales_2024",
                help="Enter an existing index name to update it, or a new name to create a new index",
                key="upload_index_name"
            )
        
        with col2:
            st.write("")  # Add some spacing
            if st.button("📊 Get Index Stats", key="upload_get_stats"):
                if index_name:
                    with st.spinner("Getting index stats..."):
                        stats = get_index_stats(app_id, admin_key, index_name)
                        if stats > 0:
                            st.success(f"📊 **{stats:,}** records in '{index_name}'")
                        elif stats == 0:
                            st.info(f"📄 Index '{index_name}' exists but is empty")
                        elif stats == -1:
                            st.warning(f"❓ Index '{index_name}' doesn't exist yet")
                        else:
                            st.error(f"❌ Failed to get stats for '{index_name}'")
                else:
                    st.warning("⚠️ Please enter an index name first")
        
        # File Upload Section
        st.subheader("📁 Upload Data File")
        uploaded_file = st.file_uploader(
            "Choose a JSON or CSV file",
            type=['json', 'csv'],
            key="upload_file_uploader"
        )
        
        # Continue with upload processing logic here (after file upload)
        if uploaded_file:
            # Process and display file info
            try:
                records = process_file(uploaded_file)
                if records:
                    st.success(f"✅ File processed successfully! Found {len(records)} records")
                    
                    # Display sample data
                    with st.expander("👀 Preview Data (First 3 Records)", expanded=False):
                        for i, record in enumerate(records[:3], 1):
                            st.json(record, expanded=False)
                    
                    # Upload configuration
                    st.subheader("⚙️ Upload Configuration")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        batch_options = [100, 500, 1000, 10000]
                        # Filter batch options to not exceed record count
                        valid_batch_options = [b for b in batch_options if b <= len(records)]
                        if not valid_batch_options:
                            valid_batch_options = [len(records)]
                        
                        batch_size = st.selectbox(
                            "Batch Size",
                            options=valid_batch_options,
                            index=0,
                            help=f"Number of records to upload per batch. File has {len(records)} records.",
                            key="upload_batch_size"
                        )
                    
                    with col2:
                        upload_mode = st.selectbox(
                            "Upload Mode",
                            options=["Add/Update Records", "Replace Index"],
                            help="Add/Update: Merge with existing data. Replace: Clear index and upload new data.",
                            key="upload_mode"
                        )
                    
                    # Show batch warning for large uploads
                    if len(records) > 500:
                        st.warning(f"⚠️ Large upload detected ({len(records)} records). Consider using smaller batch sizes for better reliability.")
                    
                    # Upload button and logic
                    if st.button("🚀 Upload to Algolia", type="primary", key="upload_button") and index_name:
                        # Validate records first - no truncation, just validation
                        fixed_records, validation_success = validate_and_fix_records(records)
                        
                        if not validation_success:
                            st.stop()  # Stop execution if validation failed
                        
                        success = upload_to_algolia(
                            app_id, admin_key, index_name, fixed_records, batch_size, 
                            upload_mode == "Replace Index"
                        )
                        
                        if success:
                            # Show toast notification for upload success
                            st.toast(f"✅ Data uploaded successfully in {st.session_state.upload_time_text}!", icon="🎉")
                            
                            st.success("🎉 Upload completed successfully!")
                            
                            # Upload Preview
                            st.subheader("📄 Upload Summary")
                            
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                st.markdown("**📊 Upload Summary**")
                                st.metric("Total Records", len(fixed_records))
                                st.metric("Index Name", index_name)
                                st.metric("Upload Mode", upload_mode)
                                st.metric("Batch Size", batch_size)
                                st.metric("File Type", uploaded_file.type)
                                st.metric("File Size", f"{uploaded_file.size / 1024:.1f} KB")
                            
                            with col2:
                                st.markdown("**🔍 Sample Records Preview**")
                                st.markdown("*First 3 records from your upload:*")
                                for i, record in enumerate(fixed_records[:3], 1):
                                    with st.expander(f"Record {i}", expanded=i==1):
                                        st.json(record, expanded=False)
                                
                                if len(fixed_records) <= 20:
                                    if st.button("📋 Show All Uploaded Records", key="show_all"):
                                        with st.expander("All Uploaded Records", expanded=True):
                                            st.json(fixed_records, expanded=False)
                                
                                # Download option for the processed data
                                processed_json = json.dumps(fixed_records, indent=2, ensure_ascii=False)
                                st.download_button(
                                    label=f"💾 Download Processed Data ({len(fixed_records)} records)",
                                    data=processed_json,
                                    file_name=f"{index_name}_processed_data_{len(fixed_records)}_records.json",
                                    mime="application/json",
                                    help="Download the processed data with objectIDs and any transformations applied",
                                    key="download_processed_data"
                                )
                    
                    elif not index_name:
                        st.warning("⚠️ Please enter an index name before uploading")
                
            except Exception as e:
                st.error(f"❌ Error processing file: {str(e)}")
        
        else:
            st.info("👆 Please upload a JSON or CSV file to get started")
    
    with right_col:
        # File Format Guide Section
        st.subheader("📋 File Format Guide")
        
        with st.expander("📖 View Upload File Types", expanded=False):
            # Create tabs for different file formats
            tab1, tab2 = st.tabs(["JSON Example", "CSV Example"])
            
            with tab1:
                st.markdown("**JSON:** Should contain either a single object or an array of objects.")
                st.code('''[
  {
    "firstname": "Jamie",
    "lastname": "Barninger",
    "zip_code": 12345
  },
  {
    "firstname": "John",
    "lastname": "Doe",
    "zip_code": null
  }
]''', language='json')
                
                st.markdown("**Key Points:**")
                st.markdown("• Array of objects or single object")
                st.markdown("• Each object becomes a record")
                st.markdown("• objectID auto-generated if missing")
                st.markdown("• Supports nested objects")
            
            with tab2:
                st.markdown("**CSV:** Comma separated, first line as header.")
                st.code('''"firstname","lastname","zip_code"
"Jamie","Barninger",12345
"John","Doe",''', language='csv')
                
                st.markdown("**Key Points:**")
                st.markdown("• First row contains headers")
                st.markdown("• Comma-separated values")
                st.markdown("• Empty values become null")
                st.markdown("• Auto-converts to JSON format")
        
        # Additional helpful info
        st.markdown("---")
        st.markdown("**💡 Tips:**")
        st.markdown("• Records auto-get objectID")
        st.markdown("• Records exceeding 10KB will be rejected")
        st.markdown("• Batch uploads for efficiency")
    
# This allows the file to be imported as a module or run standalone
if __name__ == "__main__":
    # For standalone testing, you'd need to provide hardcoded credentials
    # But when imported, this won't run
    st.error("This module needs to be called from the main app with credentials") 