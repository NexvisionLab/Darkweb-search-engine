import re

SCRIPT_TAG_REGEX = re.compile(r"<script.*?</script>", re.IGNORECASE | re.DOTALL)
STYLE_TAG_REGEX = re.compile(r"<style.*?</style>", re.IGNORECASE | re.DOTALL)
COMPRESS_WS_REGEX = re.compile(r"[\r\t ]*\n[\r\t\n ]*", re.IGNORECASE | re.DOTALL)


def break_long_words(text):
    try:
        text = text.decode('utf-8')
    except Exception as ex:
        pass
    return re.sub("([^ <>\\t\\n\\r\\f\\v]{35,70})", "\\1 ", text)


def strip_html(text):
    try:
        text = text.decode('utf-8')
    except Exception as ex:
        pass
    cleaned = re.sub(SCRIPT_TAG_REGEX, '', text)
    cleaned = re.sub(STYLE_TAG_REGEX, '', cleaned)
    cleaned = re.sub('<[^<]+?>', '', cleaned)
    cleaned = re.sub(COMPRESS_WS_REGEX, " \n ", cleaned)
    return cleaned


def utf8_conv(s):
    return str(s, "utf-8", "replace")
