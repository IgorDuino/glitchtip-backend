from ninja import Schema


def to_camel(string: str, id_string: str) -> str:
    """If a word is exactly id, make it Id"""
    return "".join(
        word if i == 0 else id_string if word == "id" else word.capitalize()
        for i, word in enumerate(string.split("_"))
    )

def to_camel_upper(string: str) -> str:
    return to_camel(string, "ID")

def to_camel_lower(string: str) -> str:
    return to_camel(string, "Id")

class CamelSchema(Schema):
    """
    Use json camel case convention by default
    Preferred camel case schema

    - event_id > eventID
    - event_number > eventNumber
    - foobar_100 > foobar100
    """

    class Config(Schema.Config):
        alias_generator = to_camel_upper
        populate_by_name = True

class CamelWithLowerIdSchema(Schema):
    '''
    Use json camel case convention by default
    For Sentry compatibility on issues
    '''
    class Config(Schema.Config):
        alias_generator = to_camel_lower
        populate_by_name = True