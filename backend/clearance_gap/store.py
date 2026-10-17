"""The local and AWS stores share the same PK/SK records and conditional commits."""
import hashlib
import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import boto3
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError


class Conflict(Exception):
    pass


class LimitExceeded(Exception):
    def __init__(self, message, retry_after):
        super().__init__(message)
        self.retry_after = retry_after


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class Store:
    def __init__(self, config):
        self.config = config
        if config.storage_mode == "sqlite":
            Path(config.database_path).parent.mkdir(parents=True, exist_ok=True)
            with self.connection() as db:
                db.execute("CREATE TABLE IF NOT EXISTS items (pk TEXT, sk TEXT, body TEXT, PRIMARY KEY(pk,sk))")
        else:
            self.aws = boto3.Session(profile_name=config.aws_profile, region_name=config.aws_region)
            self.client = self.aws.client("dynamodb")
            self.serializer, self.deserializer = TypeSerializer(), TypeDeserializer()

    def connection(self):
        db = sqlite3.connect(self.config.database_path, timeout=15)
        db.execute("PRAGMA journal_mode=WAL")
        return db

    def encode(self, item):
        # DynamoDB's serializer requires Decimal instead of floating point.
        return {key: self.serializer.serialize(value) for key, value in
                json.loads(json.dumps(item), parse_float=Decimal).items()}

    def decode(self, item):
        result = {key: self.deserializer.deserialize(value) for key, value in item.items()}
        return json.loads(json.dumps(result, default=lambda v:
                                     (int(v) if v == int(v) else float(v)) if isinstance(v, Decimal) else str(v)))

    def get(self, pk, sk):
        if self.config.storage_mode == "sqlite":
            with self.connection() as db:
                row = db.execute("SELECT body FROM items WHERE pk=? AND sk=?", (pk, sk)).fetchone()
                return json.loads(row[0]) if row else None
        item = self.client.get_item(TableName=self.config.dynamodb_table,
                                    Key=self.encode({"PK": pk, "SK": sk}), ConsistentRead=True).get("Item")
        return self.decode(item) if item else None

    def partition(self, pk):
        if self.config.storage_mode == "sqlite":
            with self.connection() as db:
                return [json.loads(r[0]) for r in db.execute(
                    "SELECT body FROM items WHERE pk=? ORDER BY sk", (pk,))]
        rows, cursor = [], None
        while True:
            args = dict(TableName=self.config.dynamodb_table, KeyConditionExpression="PK = :pk",
                        ExpressionAttributeValues=self.encode({":pk": pk}), ConsistentRead=True)
            if cursor:
                args["ExclusiveStartKey"] = cursor
            page = self.client.query(**args)
            rows.extend(self.decode(row) for row in page["Items"])
            cursor = page.get("LastEvaluatedKey")
            if not cursor:
                return rows

    def list_sessions(self, owner):
        if self.config.storage_mode == "sqlite":
            with self.connection() as db:
                rows = [json.loads(r[0]) for r in db.execute("SELECT body FROM items WHERE sk='META'")]
                return sorted([r for r in rows if r["traineeId"] == owner],
                              key=lambda r: r["createdAt"], reverse=True)
        page = self.client.query(
            TableName=self.config.dynamodb_table, IndexName="sessions-by-user",
            KeyConditionExpression="GSI1PK = :owner", ExpressionAttributeValues=self.encode({":owner": f"USER#{owner}"}),
            ScanIndexForward=False, Limit=50)
        return [self.decode(row) for row in page["Items"]]

    def commit(self, meta, updates, expected_revision, receipt=None, run_quota=None):
        pk = f"SESSION#{meta['sessionId']}"
        header = {**meta, "PK": pk, "SK": "META",
                  "GSI1PK": f"USER#{meta['traineeId']}",
                  "GSI1SK": f"SESSION#{meta['createdAt']}#{meta['sessionId']}"}
        records = [header, *[{**item, "PK": pk} for item in updates]]
        if receipt:
            records.append(receipt)
        if any(len(json.dumps(r).encode()) > 390_000 for r in records):
            raise ValueError("Record exceeds the item limit; external payload storage is required")
        if self.config.storage_mode == "sqlite":
            with self.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                existing = db.execute("SELECT body FROM items WHERE pk=? AND sk='META'", (pk,)).fetchone()
                revision = json.loads(existing[0])["revision"] if existing else None
                if revision != expected_revision:
                    raise Conflict("Session revision changed")
                if receipt and db.execute("SELECT 1 FROM items WHERE pk=? AND sk=?",
                                          (receipt["PK"], receipt["SK"])).fetchone():
                    raise Conflict("Request was already committed")
                if run_quota:
                    quota_row = db.execute("SELECT body FROM items WHERE pk=? AND sk=?",
                                           (run_quota["PK"], run_quota["SK"])).fetchone()
                    count = json.loads(quota_row[0])["runs"] if quota_row else 0
                    if count >= run_quota["limit"]:
                        raise LimitExceeded("Daily exercise limit reached. Try again after midnight UTC.",
                                            run_quota["retryAfter"])
                    counter = {key: run_quota[key] for key in ["PK", "SK"]} | {"runs": count + 1}
                    db.execute("INSERT OR REPLACE INTO items VALUES (?,?,?)",
                               (counter["PK"], counter["SK"], json.dumps(counter)))
                for record in records:
                    db.execute("INSERT OR REPLACE INTO items VALUES (?,?,?)",
                               (record["PK"], record["SK"], json.dumps(record)))
            return
        transactions = []
        for i, record in enumerate(records):
            put = {"TableName": self.config.dynamodb_table, "Item": self.encode(record)}
            if i == 0:
                if expected_revision is None:
                    put["ConditionExpression"] = "attribute_not_exists(PK)"
                else:
                    put.update(ConditionExpression="revision = :revision",
                               ExpressionAttributeValues=self.encode({":revision": expected_revision}))
            elif receipt and i == len(records) - 1:
                put["ConditionExpression"] = "attribute_not_exists(PK)"
            transactions.append({"Put": put})
        if run_quota:
            transactions.append({"Update": {
                "TableName": self.config.dynamodb_table,
                "Key": self.encode({key: run_quota[key] for key in ["PK", "SK"]}),
                "UpdateExpression": "ADD #runs :one",
                "ConditionExpression": "attribute_not_exists(#runs) OR #runs < :limit",
                "ExpressionAttributeNames": {"#runs": "runs"},
                "ExpressionAttributeValues": self.encode({":one": 1, ":limit": run_quota["limit"]}),
            }})
        try:
            self.client.transact_write_items(TransactItems=transactions)
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "TransactionCanceledException":
                reasons = exc.response.get("CancellationReasons", [])
                if run_quota and len(reasons) == len(transactions) and reasons[-1].get("Code") == "ConditionalCheckFailed":
                    raise LimitExceeded("Daily exercise limit reached. Try again after midnight UTC.",
                                        run_quota["retryAfter"]) from exc
                raise Conflict("Concurrent update or duplicate request") from exc
            raise
