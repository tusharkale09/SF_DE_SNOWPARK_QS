import time

import toml
from snowflake.snowpark import Session

config = toml.load("../.devcontainer/connections.toml")
default_connection = config["default"]

POS_TABLES = ['country', 'franchise', 'location', 'menu', 'truck', 'order_header', 'order_detail']
CUSTOMER_TABLES = ['customer_loyalty']
TABLE_DICT = {
    "pos": {"schema": "RAW_POS", "tables": POS_TABLES},
    "customer": {"schema": "RAW_CUSTOMER", "tables": CUSTOMER_TABLES}
}


def create_parquet_external_stage(session, external_stage_name,
                                  file_format_name="parquet_format",
                                  url_to_stage='s3://sfquickstarts/data-engineering-with-snowpark-python/'):
    try:
        # Create a file format
        create_file_format_sql = f"""
                CREATE OR REPLACE FILE FORMAT {file_format_name} 
                TYPE = PARQUET
                COMPRESSION = 'SNAPPY'
                """
        # Execute the statement
        session.sql(create_file_format_sql).collect()

        # Create a stage
        create_stage_sql = f"""
                CREATE OR REPLACE STAGE {external_stage_name}
                FILE_FORMAT = parquet_format
                URL = '{url_to_stage}';
                """
        session.sql(create_stage_sql).collect()

        while not external_stage_exists(session, external_stage_name):
            print(f"Waiting for external stage {external_stage_name} to be created...")
            time.sleep(5)
        print(f"External stage {external_stage_name} created successfully.")

    except Exception as e:
        print(f"Failed to create external stage {external_stage_name}. Error: {str(e)}")


def external_stage_exists(session, stage_name):
    sql_query = f"""
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.STAGES
            WHERE STAGE_NAME = '{stage_name}';
        """
    result = session.sql(sql_query).collect()

    return result[0][0] > 0


def load_raw_table(session, table_name=None, s3dir=None, year=None, schema=None, stage_name='FROSTBYTE_RAW_STAGE'):
    session.use_schema(schema)
    if year is None:
        location = "@external.frostbyte_raw_stage/{}/{}".format(s3dir, table_name)
    else:
        print('\tLoading year {}'.format(year))
        location = "@external.frostbyte_raw_stage/{}/{}/year={}".format(s3dir, table_name, year)
    if not external_stage_exists(session, stage_name):
        print(f"Stage {stage_name} does not exist. Creating.")
        create_parquet_external_stage(session, stage_name)
    # we can infer schema using the parquet read option
    df = session.read.option("compression", "snappy").parquet(location)
    df.copy_into_table("{}".format(table_name))


# '@"SFTUTORDATAEGNRING"."RAW_POS"."FROSTBYTE_RAW_STAGE"/pos/country/country.snappy.parquet'

# SNOWFLAKE ADVANTAGE: Warehouse elasticity (dynamic scaling)

def load_all_raw_tables(session):
    _ = session.sql("ALTER WAREHOUSE HOL_WH SET WAREHOUSE_SIZE = XLARGE WAIT_FOR_COMPLETION = TRUE").collect()

    for s3dir, data in TABLE_DICT.items():
        table_names = data['tables']
        schema = data['schema']
        for name in table_names:
            print("Loading {}".format(name))
            # Only load the first 3 years of data for the order tables at this point
            # We will load the 2022 data later in the lab

            if name in ['order_header', 'order_detail']:
                for year in ['2019', '2020', '2021']:
                    load_raw_table(session, table_name=name, s3dir=s3dir, year=year, schema=schema)
            else:
                load_raw_table(session, table_name=name, s3dir=s3dir, schema=schema)

    _ = session.sql("ALTER WAREHOUSE HOL_WH SET WAREHOUSE_SIZE = XSMALL").collect()


def validate_raw_tables(session):
    # check column names from the inferred schema
    for tname in POS_TABLES:
        print('{}: \n\t{}\n'.format(tname, session.table('RAW_POS.{}'.format(tname)).columns))

    for tname in CUSTOMER_TABLES:
        print('{}: \n\t{}\n'.format(tname, session.table('RAW_CUSTOMER.{}'.format(tname)).columns))


# For local debugging
if __name__ == "__main__":
    # Create a local Snowpark session
    with Session.builder.configs(default_connection).getOrCreate() as session:
        load_all_raw_tables(session)
#        validate_raw_tables(session)
