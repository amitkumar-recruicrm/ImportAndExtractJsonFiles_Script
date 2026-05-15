import os
import glob
import json
import mysql.connector


def extract_keys(data, keys):
    """Extract top-level keys from the JSON data."""
    if isinstance(data, dict):
        for key in data.keys():
            keys.add(key)
    elif isinstance(data, list):
        for item in data:
            extract_keys(item, keys)

def read_json_lines(json_file):
    """Read a JSON Lines file and return a list of JSON objects."""
    with open(json_file, 'r', encoding='utf-8') as file:
        return [json.loads(line) for line in file if line.strip()]  # Parse each line as JSON

def get_data_type(value):
    """Determine the MySQL data type based on the Python value type."""
    if isinstance(value, str):
        return 'LONGTEXT DEFAULT NULL'
    elif isinstance(value, int):
        return 'INT DEFAULT NULL'
    elif isinstance(value, float):
        return 'FLOAT DEFAULT NULL'
    elif isinstance(value, bool):
        return 'BOOLEAN DEFAULT NULL'
    elif isinstance(value, list) or isinstance(value, dict):
        return 'JSON DEFAULT NULL'  # Store as JSON in JSON field
    return 'LONGTEXT DEFAULT NULL'  # Default fallback for unrecognized types

def generate_create_table_sql(table_name, data):
    """Generate SQL for creating a MySQL table based on keys and their types."""
    columns = []
    for record in data:
        for key, value in record.items():
            mysql_type = get_data_type(value)
            columns.append(f"`{key}` {mysql_type}")

    # Remove duplicates in columns to prevent SQL errors
    unique_columns = {col.split()[0]: col for col in columns}
    
    columns_sql = ",\n  ".join(unique_columns.values())
    create_table_sql = f"CREATE TABLE IF NOT EXISTS `{table_name}` (\n  {columns_sql}\n);"
    return create_table_sql

def execute_sql_command(sql_command, db_config):
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()
        cursor.execute(sql_command)
        connection.commit()
    except mysql.connector.Error as err:
        print(f"Error: {err}")
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def create_database_if_not_exists(db_config):
    try:
        # Connect without selecting database first
        connection = mysql.connector.connect(
            host=db_config["host"],
            user=db_config["user"],
            password=db_config["password"]
        )

        cursor = connection.cursor()
        db_name = db_config["database"]
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
        print(f"Database created or already existed! ({db_name})")

        cursor.close()
        connection.close()
        
    except Exception as e:
        print(f"Error creating database: {e}")

def insert_json_records(json_file, table_name, db_config):
    MAX_LENGTH = 65535  # Set based on your database column's limit

    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()
        
        # Read JSON data
        data = read_json_lines(json_file)

        # Ensure data is in a list format
        if isinstance(data, dict):
            data = [data]

        # Get the existing columns in the table
        cursor.execute(f"SHOW COLUMNS FROM `{table_name}`")
        existing_columns = {column[0] for column in cursor.fetchall()}

        # Insert each record
        for record in data:
            # Convert lists and dicts to JSON strings
            for key, value in record.items():
                if isinstance(value, str) and len(value) > MAX_LENGTH:
                    record[key] = value[:MAX_LENGTH]  # Truncate the value
                elif isinstance(value, list) or isinstance(value, dict):
                    record[key] = json.dumps(value)  # Convert list/dict to JSON string

            columns = ', '.join(f"`{key}`" for key in record.keys())
            placeholders = ', '.join('%s' for _ in record)
            values = tuple(record.values())
            
            insert_sql = f"INSERT INTO `{table_name}` ({columns}) VALUES ({placeholders})"
            try:
                cursor.execute(insert_sql, values)
            except mysql.connector.Error as err:
                print(f"Error inserting row: {err}, Data: {record}")
                continue  # Skip this row and move to the next
        
        connection.commit()
    
    except mysql.connector.Error as err:
        print(f"Error: {err}")
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()



# Example usage

if __name__ == "__main__":

    folder_path = "/Users/amit/Documents/Work/Data Migrations/completed/BaanExecutives (LOXO)/data 2/baan-executives/"  # Folder containing all .jsonl files
    db_config = {
        'user': 'root',
        'password': '12345678',
        'host': 'localhost',
        'database': 'BaanEL2'
    }

    # Step 0: Create database if not exists
    create_database_if_not_exists(db_config)

    # Get all .jsonl files from the folder
    json_files = glob.glob(os.path.join(folder_path, "*.jsonl"))
  
    # use this code block - If you need to skip few and import rest of the files.
    skip_files = [] 
    skip_files = [folder_path + file for file in skip_files]
    json_files = [json_file for json_file in json_files if json_file not in skip_files]

    # use this code block - If you need to import few and skip rest of the files.
    # import_only_files = ["email_templates.jsonl"] 
    # import_only_files = [folder_path + file for file in import_only_files]
    # json_files = [json_file for json_file in json_files if json_file in import_only_files]


    print(json_files)

    for json_file_path in json_files:

        # Use filename (without extension) as table name
        table_name = os.path.splitext(os.path.basename(json_file_path))[0]
        print(f"Processing file: {json_file_path}")
        print(f"Creating table: {table_name}")

        # Step 1: Read JSON Lines file and generate create table SQL
        data = read_json_lines(json_file_path)
        create_table_sql = generate_create_table_sql(table_name, data)
        execute_sql_command(create_table_sql, db_config)

        # Step 2: Insert JSON records into created table
        insert_json_records(json_file_path, table_name, db_config)
        print(f"Finished importing {json_file_path}\n")
