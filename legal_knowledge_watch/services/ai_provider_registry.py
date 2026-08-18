_PROVIDER_CLASSES = {}


def register_provider(provider_class):
    if provider_class.provider_type in _PROVIDER_CLASSES:
        raise RuntimeError(
            f"Duplicate AI provider_type: {provider_class.provider_type}"
        )
    _PROVIDER_CLASSES[provider_class.provider_type] = provider_class
    return provider_class


def get_provider(provider_record):
    try:
        provider_class = _PROVIDER_CLASSES[provider_record.provider_type]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported AI provider_type: {provider_record.provider_type}"
        ) from exc
    return provider_class(provider_record)
