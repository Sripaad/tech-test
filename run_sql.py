from google.cloud import bigquery
from google.oauth2.service_account import Credentials
from tabulate import tabulate
import json
from dotenv import load_dotenv
import os
from solution import process_query

load_dotenv()

# Dummy service account JSON - Replace this with your actual service account JSON content
SERVICE_ACCOUNT_JSON = os.getenv("SERVICE_ACCOUNT_JSON")

# BigQuery Default Dataset - Replace this with your actual dataset name
DEFAULT_DATASET = os.getenv("DEFAULT_DATASET")

# Limit the number of rows to fetch
MAX_RESULTS = os.getenv("MAX_RESULTS") or 10

if SERVICE_ACCOUNT_JSON is None:
    raise ValueError("SERVICE_ACCOUNT_JSON is not set in the environment variables.")

if DEFAULT_DATASET is None:
    raise ValueError("DEFAULT_DATASET is not set in the environment variables.")


def query_bigquery(sql_query: str):
    """
    Sends a SQL query to BigQuery, fetches the first 100 rows and total row count,
    and prints them in a formatted table.

    Args:
        sql_query (str): The SQL query string to execute.
    """
    try:
        # Create credentials from the embedded JSON string
        credentials = Credentials.from_service_account_info(
            json.loads(SERVICE_ACCOUNT_JSON)
        )

        # Initialize BigQuery client
        client = bigquery.Client(
            credentials=credentials, project=credentials.project_id
        )

        # Configure the job with the default dataset
        job_config = bigquery.QueryJobConfig(default_dataset=DEFAULT_DATASET)

        # Execute the query
        query_job = client.query(sql_query, job_config=job_config)
        result = query_job.result(
            max_results=int(MAX_RESULTS)
        )  # Waits for job to complete

        # Get total rows
        total_rows = result.total_rows

        rows = list(result)

        # Print results
        if rows:
            print(f"Total Rows: {total_rows}")
            print(f"First {MAX_RESULTS} Rows:")
            headers = rows[0].keys()  # Get column headers
            data = [
                dict(row).values() for row in rows
            ]  # Convert rows to list of values
            print(tabulate(data, headers=headers, tablefmt="grid"))
        else:
            print("Query returned no results.")
        return True
    
    except Exception as e:
        print(f"An error occurred: {e}")
        return False

def _test_run(run_all: bool = False, additional: bool = False) -> None:
    with open("./test_queries.json") as f:
        test_queries = json.load(f)
    if additional:
        with open("./test_queries_additional.json") as f:
            new_queries = json.load(f)
            test_queries['test_queries'].extend(new_queries['test_queries'])
    if not run_all:
        sample_query = "SELECT * FROM orders"
        query_bigquery(sample_query)
        print("||--------------------||")

    else:
        results = []
        for i, test_query in enumerate(test_queries['test_queries']):
            print(f"\nExecuting Test {i}: {test_query['query_string']}")
            processed_query = process_query(
                test_query['semantic_layer_definition'],
                test_query['query']
            )
            print("Processed Query: ", processed_query)
            
            q = query_bigquery(processed_query)
            test_passed = bool(q)
            results.append(test_passed)
            
            if test_passed:
                print("✅ Test Passed")
            else:
                print(f"❌ Test Failed: {test_query['query_string']}")
            
            print("||--------------------||")
            
        passed_count = sum(results)
        failed_count = len(results) - passed_count
        
        print(f"\n📊 Test Summary:")
        print(f"Passed: {passed_count}")
        print(f"Failed: {failed_count}")
        print(f"Total: {len(results)}")

# Example Usage
if __name__ == "__main__":
    print("Run single sample test")
    _test_run()
    print("Running for all test queries")
    _test_run(run_all=True, additional=True)
