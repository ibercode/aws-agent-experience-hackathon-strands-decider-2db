from boto3.dynamodb.types import TypeDeserializer, TypeSerializer

from clearance_gap.store import Store


def test_dynamodb_preserves_integer_cursors_and_fractional_metrics():
    store = Store.__new__(Store)
    store.serializer, store.deserializer = TypeSerializer(), TypeDeserializer()
    result = store.decode(store.encode({"sequence": 12, "latency": 1.25, "nested": {"version": 3}}))
    assert isinstance(result["sequence"], int)
    assert isinstance(result["nested"]["version"], int)
    assert result["latency"] == 1.25
