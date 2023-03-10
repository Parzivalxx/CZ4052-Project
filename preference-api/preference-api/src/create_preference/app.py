import json
from dynamo import get_dynamo_table
from typing import Dict, Union


def lambda_handler(event, context):
    print(event)

    if not event['body']:
        return {"statusCode": 400,
                "headers": {},
                "body": "Bad request"}

    preference: Dict[str, Union[int, str]] = json.loads(event["body"])

    try:
        db_response = get_dynamo_table().put_item(Item=preference)
        print(db_response)
        return {"statusCode": 201,
                "headers": {},
                "body": json.dumps(preference)}

    except Exception as e:
        print(e)
        return {"statusCode": 500,
                "headers": {},
                "body": "Internal Server Error"}
