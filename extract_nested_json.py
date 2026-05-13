import mysql.connector
import json


db_config = {
    "host": "localhost",
    "user": "root",
    "password": "12345678",
    "database": "baane"
}


def get_all_tables(connection):
    cursor = connection.cursor()
    cursor.execute("SHOW TABLES")
    tables = [row[0] for row in cursor.fetchall()]
    cursor.close()
    return tables


def get_table_columns(connection, table_name):
    cursor = connection.cursor(dictionary=True)
    cursor.execute(f"SHOW COLUMNS FROM `{table_name}`")
    columns = cursor.fetchall()
    cursor.close()
    return columns


def is_json(value):
    if not value:
        return False
    try:
        json.loads(value)
        return True
    except:
        return False


def get_all_json_keys(connection, table_name, column_name):
    """
    Scan all rows of a column and collect every JSON key
    so no field is missed even if it exists in only a few records
    """
    all_keys = {}
    cursor = connection.cursor()

    cursor.execute(f"""
        SELECT `{column_name}`
        FROM `{table_name}`
        WHERE `{column_name}` IS NOT NULL
    """)

    rows = cursor.fetchall()
    cursor.close()

    for row in rows:
        value = row[0]

        if not is_json(value):
            continue

        try:
            parsed = json.loads(value)

            # If JSON is dict
            if isinstance(parsed, dict):
                parsed = [parsed]

            # If JSON is list of dicts
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        for key, val in item.items():
                            if key.lower() == "id":
                                continue

                            # Store datatype based on first found value
                            if key not in all_keys:
                                all_keys[key] = mysql_type(val)

        except:
            continue

    return all_keys


def mysql_type(value):
    if isinstance(value, bool):
        return "BOOLEAN"
    elif isinstance(value, int):
        return "BIGINT"
    elif isinstance(value, float):
        return "DOUBLE"
    elif isinstance(value, str):
        return "TEXT"
    elif isinstance(value, (dict, list)):
        return "JSON"
    else:
        return "TEXT"


def create_json_table(connection, parent_table, json_column):
    """
    Create table using ALL keys found across all records
    """
    new_table = f"{parent_table}_{json_column}"
    all_keys = get_all_json_keys(connection, parent_table, json_column)

    if not all_keys:
        return

    columns_sql = [
        "id BIGINT AUTO_INCREMENT PRIMARY KEY",
        f"{parent_table}_id BIGINT"
    ]

    for field, field_type in all_keys.items():
        columns_sql.append(f"`{field}` {field_type}")

    create_sql = f"""
        CREATE TABLE IF NOT EXISTS `{new_table}` (
            {", ".join(columns_sql)}
        )
    """

    cursor = connection.cursor()
    cursor.execute(create_sql)
    connection.commit()
    cursor.close()

    print(f"Created table: {new_table}")

def create_array_table(connection, table_name, parent_table):
    cursor = connection.cursor()

    create_sql = f"""
        CREATE TABLE IF NOT EXISTS `{table_name}` (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            `{parent_table}_id` BIGINT,
            value TEXT
        )
    """

    cursor.execute(create_sql)
    connection.commit()
    cursor.close()

    print(f"Created array table: {table_name}")


def insert_array_data(connection, table_name, parent_id, parent_table, values):
    cursor = connection.cursor()

    insert_sql = f"""
        INSERT INTO `{table_name}` (
            `{parent_table}_id`,
            `value`
        )
        VALUES (%s, %s)
    """

    for val in values:
        # If nested dict/list inside array, store as JSON string
        if isinstance(val, (dict, list)):
            val = json.dumps(val)

        try:
            cursor.execute(insert_sql, (parent_id, val))
        except Exception as e:
            print(f"Insert failed in {table_name}: {e}")

    connection.commit()
    cursor.close()

    print(f"Data inserted into array table: {table_name}")

def insert_json_data(connection, parent_table, json_column):
    """
    Insert all JSON values safely using dynamic fields
    """
    new_table = f"{parent_table}_{json_column}"

    cursor = connection.cursor(dictionary=True)
    cursor.execute(f"""
        SELECT id, `{json_column}`
        FROM `{parent_table}`
        WHERE `{json_column}` IS NOT NULL
    """)

    rows = cursor.fetchall()
    cursor.close()

    insert_cursor = connection.cursor()

    for row in rows:
        parent_id = row["id"]
        json_value = row[json_column]

        if not is_json(json_value):
            continue

        try:
            parsed = json.loads(json_value)

            if isinstance(parsed, dict):
                parsed = [parsed]

            if not isinstance(parsed, list):
                continue

            for item in parsed:
                if not isinstance(item, dict):
                    continue

                cleaned_item = {}

                for key, value in item.items():
                    if key.lower() == "id":
                        continue

                    if isinstance(value, (list, dict)):
                        cleaned_item[key] = json.dumps(value)
                    else:
                        cleaned_item[key] = value

                columns = [f"{parent_table}_id"] + list(cleaned_item.keys())
                values = [parent_id] + list(cleaned_item.values())

                placeholders = ", ".join(["%s"] * len(values))
                column_names = ", ".join([f"`{col}`" for col in columns])

                insert_sql = f"""
                    INSERT INTO `{new_table}` ({column_names})
                    VALUES ({placeholders})
                """

                try:
                    insert_cursor.execute(insert_sql, values)
                except Exception as e:
                    print(f"Insert failed in {new_table}: {e}")

        except Exception as e:
            print(f"JSON parse failed in {parent_table}.{json_column}: {e}")

    connection.commit()
    insert_cursor.close()

    print(f"Data inserted into: {new_table}")

def insert_direct_array_data(connection, parent_table, column_name, array_table):
    cursor = connection.cursor(dictionary=True)

    cursor.execute(f"""
        SELECT id, `{column_name}`
        FROM `{parent_table}`
        WHERE `{column_name}` IS NOT NULL
    """)

    rows = cursor.fetchall()
    cursor.close()

    for row in rows:
        parent_id = row["id"]
        value = row[column_name]

        if not is_json(value):
            continue

        parsed = json.loads(value)

        if isinstance(parsed, list):
            insert_array_data(
                connection,
                array_table,
                parent_id,
                parent_table,
                parsed
            )

    print(f"Inserted direct array data into: {array_table}")

def process_database():
    connection = mysql.connector.connect(**db_config)

    tables = get_all_tables(connection)
    # Tables to skip
    # skip_tables = ["companies", "people","activities","agency","deals","email_templates","task_boards"]
    # skip_tables = ["Jobs"]
    # tables = [table for table in tables if table not in skip_tables]
    
    # use this code block - If you need to import few and skip rest of the files.
    expand_only_tables = ["people"]
    tables = [table for table in tables if table in expand_only_tables]
    
    for table in tables:
        print(f"\nProcessing table: {table}")

        columns = get_table_columns(connection, table)

        for column in columns:
            column_name = column["Field"]

            if column_name == "id":
                continue

            cursor = connection.cursor()

            cursor.execute(f"""
                SELECT `{column_name}`
                FROM `{table}`
                WHERE `{column_name}` IS NOT NULL
                LIMIT 1
            """)

            row = cursor.fetchone()
            cursor.close()

            if not row:
                continue

            try:
                parsed = json.loads(row[0])

                # CASE 1 → Direct array like ["a", "b"] or [123, 456]
                if isinstance(parsed, list) and (
                    len(parsed) == 0 or not isinstance(parsed[0], dict)
                ):
                    print(f"Direct array found in: {table}.{column_name}")

                    array_table = f"{table}_{column_name}"

                    create_array_table(
                        connection,
                        array_table,
                        table
                    )

                    insert_direct_array_data(
                        connection,
                        table,
                        column_name,
                        array_table
                    )

                # CASE 2 → JSON object or list of objects
                else:
                    all_keys = get_all_json_keys(
                        connection,
                        table,
                        column_name
                    )

                    if all_keys:
                        print(f"JSON object found in: {table}.{column_name}")

                        create_json_table(
                            connection,
                            table,
                            column_name
                        )

                        insert_json_data(
                            connection,
                            table,
                            column_name
                        )

            except:
                continue

    connection.close()
    print("\nCompleted processing all tables.")


if __name__ == "__main__":
    process_database()