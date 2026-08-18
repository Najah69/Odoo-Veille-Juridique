CONNECTOR_REGISTRY = {}


def register_connector(connector_class):
    if connector_class.code in CONNECTOR_REGISTRY:
        raise RuntimeError(f"Duplicate connector code: {connector_class.code}")
    CONNECTOR_REGISTRY[connector_class.code] = connector_class
    return connector_class


def get_connector(code):
    try:
        return CONNECTOR_REGISTRY[code]
    except KeyError as exc:
        raise ValueError(f"Unsupported connector: {code}") from exc
