import ast
import base64
import html
import inspect
import json
import os.path
import random
import re
import shlex
import threading
import time
import traceback
import zlib
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from enum import Enum
from html.parser import HTMLParser
from struct import unpack
from typing import Any, Callable, Dict, List, Optional, Tuple, Union, final
from urllib.parse import parse_qs, urlencode, urlparse

from android.util import TypedValue  # type: ignore
from android.view import Gravity, View  # type: ignore
from android.widget import LinearLayout  # type: ignore
from android.widget import FrameLayout, TextView  # type: ignore
from android_utils import OnClickListener
from android_utils import log as logcat
from android_utils import run_on_ui_thread
from base_plugin import (BasePlugin, HookResult, HookStrategy, MenuItemData,
                         MenuItemType, MethodHook)
from client_utils import (RequestCallback, get_account_instance,
                          get_connections_manager, get_last_fragment,
                          get_media_data_controller, get_messages_controller,
                          get_send_messages_helper, get_user_config,
                          run_on_queue, send_message, send_request)
from com.exteragram.messenger.plugins import PluginsController  # type: ignore
from com.exteragram.messenger.plugins.ui import PluginSettingsActivity  # type: ignore
from java import dynamic_proxy, jarray, jfloat, jint, jlong  # type: ignore
from java.io import (BufferedReader, File, InputStreamReader,  # type: ignore
                     IOException)
from java.lang import (Double, Integer, InterruptedException, Runtime,  # type: ignore
                       String)
from java.lang import System as JavaSystem  # type: ignore
from java.util import ArrayList, Locale  # type: ignore
from org.telegram.messenger import (AndroidUtilities,  # type: ignore
                                    ApplicationLoader,
                                    LocaleController, MessageObject,
                                    SendMessagesHelper, Utilities)
from org.telegram.tgnet import TLRPC  # type: ignore
from org.telegram.ui.ActionBar import BottomSheet  # type: ignore
from org.telegram.ui.ActionBar import Theme  # type: ignore
from org.telegram.ui.Cells import CheckBoxCell  # type: ignore
from org.telegram.ui.Components import (BackupImageView,  # type: ignore
                                        CheckBox2, LayoutHelper,
                                        LineProgressView)
from ui.alert import AlertDialogBuilder
from ui.bulletin import BulletinHelper
from ui.settings import Divider, Header, Input

import plugins_manager
from hook_utils import find_class, get_private_field

__name__ = "CactusLib"
__description__ = "Cactus's library with full-fledged help, limitless features for text/uri commands, plugins import/export and more than!"
__icon__ = "CactusPlugins/0"
__id__ = "cactuslib"
__version__ = "1.2.0"
__author__ = "@CactusPlugins"
__min_version__ = "11.12.0"
__all__ = ("CactusUtils", "command", "uri", "HookResult", "HookStrategy", "MenuItemData", "MenuItemType")

LVLS = ["DEBUG", "INFO", "WARN", "ERROR"]


##############################   Markdown & HTML parsers   ##############################
# Original parts (modified) of code from https://github.com/KurimuzonAkuma/pyrogram/blob/31fa1e48b6258f246289c5561a391eba584d546d/pyrogram/parser/html.py
# Original parts (modified) of code from https://github.com/KurimuzonAkuma/pyrogram/blob/31fa1e48b6258f246289c5561a391eba584d546d/pyrogram/parser/markdown.py

def add_surrogates(text: str) -> str:
    return re.compile(r"[\U00010000-\U0010FFFF]").sub(
        lambda match:
        "".join(chr(i) for i in unpack("<HH", match.group().encode("utf-16le"))),
        text
    )


def remove_surrogates(text: str) -> str:
    return text.encode("utf-16", "surrogatepass").decode("utf-16")


class TLEntityType(Enum):
    CODE = 'code'
    PRE = 'pre'
    STRIKETHROUGH = 'strikethrough'
    TEXT_LINK = 'text_link'
    BOLD = 'bold'
    ITALIC = 'italic'
    UNDERLINE = 'underline'
    SPOILER = 'spoiler'
    CUSTOM_EMOJI = 'custom_emoji'
    BLOCKQUOTE = 'blockquote'


@dataclass
class RawEntity:
    TLRPC_ENTITIES_MAP = {
        TLEntityType.CODE: TLRPC.TL_messageEntityCode,
        TLEntityType.PRE: TLRPC.TL_messageEntityPre,
        TLEntityType.STRIKETHROUGH: TLRPC.TL_messageEntityStrike,
        TLEntityType.TEXT_LINK: TLRPC.TL_messageEntityTextUrl,
        TLEntityType.BOLD: TLRPC.TL_messageEntityBold,
        TLEntityType.ITALIC: TLRPC.TL_messageEntityItalic,
        TLEntityType.UNDERLINE: TLRPC.TL_messageEntityUnderline,
        TLEntityType.SPOILER: TLRPC.TL_messageEntitySpoiler,
        TLEntityType.CUSTOM_EMOJI: TLRPC.TL_messageEntityCustomEmoji,
        TLEntityType.BLOCKQUOTE: TLRPC.TL_messageEntityBlockquote
    }

    type: TLEntityType
    offset: int
    length: int
    language: Optional[str] = None
    url: Optional[str] = None
    document_id: Optional[int] = None
    collapsed: Optional[bool] = None

    def to_tlrpc_object(self):
        entity = self.TLRPC_ENTITIES_MAP[self.type]()
        entity.offset = self.offset
        entity.length = self.length

        if self.language is not None:
            entity.language = self.language
        if self.url is not None:
            entity.url = self.url
        if self.document_id is not None:
            entity.document_id = self.document_id
        if self.collapsed is not None:
            entity.collapsed = self.collapsed
        
        return entity


class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = ""
        self.entities = []
        self.tag_entities = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        extra = {}

        if tag in ["b", "strong"]:
            _type = TLEntityType.BOLD
        elif tag in ["i", "em"]:
            _type = TLEntityType.ITALIC
        elif tag == "u":
            _type = TLEntityType.UNDERLINE
        elif tag in ["s", "del", "strike"]:
            _type = TLEntityType.STRIKETHROUGH
        elif tag == "blockquote":
            _type = TLEntityType.BLOCKQUOTE
            extra["collapsed"] = "expandable" in attrs or "collapsed" in attrs
        elif tag == "code":
            _type = TLEntityType.CODE
        elif tag == "pre":
            _type = TLEntityType.PRE
            extra["language"] = attrs.get("language", attrs.get("lang", ""))
        elif tag == "spoiler":
            _type = TLEntityType.SPOILER
        elif tag == "a":
            url = attrs.get("href", "")
            _type = TLEntityType.TEXT_LINK
            extra["url"] = url
        elif tag == "emoji":
            _type = TLEntityType.CUSTOM_EMOJI
            custom_emoji_id = int(attrs.get("id"))
            extra["document_id"] = custom_emoji_id
        else:
            return

        if tag not in self.tag_entities:
            self.tag_entities[tag] = []

        self.tag_entities[tag].append(
            RawEntity(
                type=_type,
                offset=len(self.text),
                length=0,
                **extra
            ))

    def handle_data(self, data):
        data = html.unescape(data)

        for entities in self.tag_entities.values():
            for entity in entities:
                entity.length += len(data)

        self.text += data

    def handle_endtag(self, tag):
        try:
            self.entities.append(self.tag_entities[tag].pop())
        except (KeyError, IndexError):
            pass
        else:
            if not self.tag_entities[tag]:
                self.tag_entities.pop(tag)


class HTML:
    @staticmethod
    def parse(text: str) -> dict:
        text = re.sub(r"^\s*(<[\w<>=\s\"]*>)\s*", r"\1", text)
        text = re.sub(r"\s*(</[\w</>]*>)\s*$", r"\1", text)

        parser = Parser()
        parser.feed(add_surrogates(text))
        parser.close()

        if parser.tag_entities:
            unclosed_tags = []

            for tag, entities in parser.tag_entities.items():
                unclosed_tags.append(f"<{tag}> (x{len(entities)})")

        entities = []

        for entity in parser.entities:
            if entity.length == 0:
                continue

            entities.append(entity)

        entities = list(filter(lambda x: x.length > 0, entities))

        return {
            "message": remove_surrogates(parser.text),
            "entities": sorted(entities, key=lambda e: e.offset)
        }

    @staticmethod
    def unparse(text: str, entities: list) -> str:
        def parse_one(entity):
            """
            Parses a single entity and returns (start_tag, start), (end_tag, end)
            """
            entity_type = entity.type
            start = entity.offset
            end = start + entity.length

            if entity_type in (
                TLEntityType.BOLD,
                TLEntityType.ITALIC,
                TLEntityType.UNDERLINE,
                TLEntityType.STRIKETHROUGH,
            ):
                name = entity_type.name[0].lower()
                start_tag = f"<{name}>"
                end_tag = f"</{name}>"
            elif entity_type == TLEntityType.PRE:
                name = entity_type.name.lower()
                language = getattr(entity, "language", "") or ""
                start_tag = f'<{name} language="{language}">' if language else f"<{name}>"
                end_tag = f"</{name}>"
            elif entity_type == TLEntityType.BLOCKQUOTE:
                name = entity_type.name.lower()
                expandable = getattr(entity, "expandable", False)
                start_tag = f'<{name}{" expandable" if expandable else ""}>'
                end_tag = f"</{name}>"
            elif entity_type in (
                TLEntityType.CODE,
                TLEntityType.SPOILER,
            ):
                name = entity_type.name.lower()
                start_tag = f"<{name}>"
                end_tag = f"</{name}>"
            elif entity_type == TLEntityType.TEXT_LINK:
                url = entity.url
                start_tag = f'<a href="{url}">'
                end_tag = "</a>"
            elif entity_type == TLEntityType.CUSTOM_EMOJI:
                custom_emoji_id = entity.custom_emoji_id
                start_tag = f'<emoji id="{custom_emoji_id}">'
                end_tag = "</emoji>"
            else:
                return

            return (start_tag, start), (end_tag, end)

        def recursive(entity_i: int) -> int:
            """
            Takes the index of the entity to start parsing from, returns the number of parsed entities inside it.
            Uses entities_offsets as a stack, pushing (start_tag, start) first, then parsing nested entities,
            and finally pushing (end_tag, end) to the stack.
            No need to sort at the end.
            """
            this = parse_one(entities[entity_i])
            if this is None:
                return 1
            (start_tag, start), (end_tag, end) = this
            entities_offsets.append((start_tag, start))
            internal_i = entity_i + 1
            # while the next entity is inside the current one, keep parsing
            while internal_i < len(entities) and entities[internal_i].offset < end:
                internal_i += recursive(internal_i)
            entities_offsets.append((end_tag, end))
            return internal_i - entity_i
        
        text = add_surrogates(text)

        entities_offsets = []

        # probably useless because entities are already sorted by telegram
        entities.sort(key=lambda e: (e.offset, -e.length))

        # main loop for first-level entities
        i = 0
        while i < len(entities):
            i += recursive(i)

        if entities_offsets:
            last_offset = entities_offsets[-1][1]
            # no need to sort, but still add entities starting from the end
            for entity, offset in reversed(entities_offsets):
                text = text[:offset] + entity + html.escape(text[offset:last_offset]) + text[last_offset:]
                last_offset = offset

        return remove_surrogates(text)


BOLD_DELIM = "*"
ITALIC_DELIM = "_"
UNDERLINE_DELIM = "__"
STRIKE_DELIM = "~"
SPOILER_DELIM = "||"
CODE_DELIM = "`"
PRE_DELIM = "```"
BLOCKQUOTE_DELIM = ">"
BLOCKQUOTE_EXPANDABLE_DELIM = "**>"
BLOCKQUOTE_EXPANDABLE_END_DELIM = "||"

MARKDOWN_RE = re.compile(r"({d})|(!?)\[(.+?)\]\((.+?)\)".format(
    d="|".join(
        ["".join(i) for i in [
            [rf"\{j}" for j in i]
            for i in [
                PRE_DELIM,
                CODE_DELIM,
                STRIKE_DELIM,
                UNDERLINE_DELIM,
                ITALIC_DELIM,
                BOLD_DELIM,
                SPOILER_DELIM
            ]
        ]]
    )))

OPENING_TAG = "<{}>"
CLOSING_TAG = "</{}>"
URL_MARKUP = '<a href="{}">{}</a>'
EMOJI_MARKUP = "<emoji id={}>{}</emoji>"
FIXED_WIDTH_DELIMS = [CODE_DELIM, PRE_DELIM]


def replace_once(source: str, old: str, new: str, start: int):
    return source[:start] + source[start:].replace(old, new, 1)


class Markdown:
    @staticmethod
    def escape_and_create_quotes(text: str, strict: bool):
        text_lines: List[Union[str, None]] = text.splitlines()

        # Indexes of Already escaped lines
        html_escaped_list: List[int] = []

        # Temporary Queue to hold lines to be quoted
        to_quote_list: List[Tuple[int, str]] = []

        def create_blockquote(expandable: bool = False) -> None:
            """
            Merges all lines in quote_queue into first line of queue
            Encloses that line in html quote
            Replaces rest of the lines with None placeholders to preserve indexes
            """
            if len(to_quote_list) == 0:
                return

            joined_lines = "\n".join([i[1] for i in to_quote_list])

            first_line_index, _ = to_quote_list[0]
            text_lines[first_line_index] = (
                f"<blockquote{' expandable' if expandable else ''}>{joined_lines}</blockquote>"
            )

            for line_to_remove in to_quote_list[1:]:
                text_lines[line_to_remove[0]] = None

            to_quote_list.clear()

        # Handle Expandable Quote
        inside_blockquote = False
        for index, line in enumerate(text_lines):
            if line.startswith(BLOCKQUOTE_EXPANDABLE_DELIM) and not inside_blockquote:
                delim_stripped_line = line[len(BLOCKQUOTE_EXPANDABLE_DELIM) + (1 if line.startswith(f"{BLOCKQUOTE_EXPANDABLE_DELIM} ") else 0) :]
                parsed_line = (
                    html.escape(delim_stripped_line) if strict else delim_stripped_line
                )

                to_quote_list.append((index, parsed_line))
                html_escaped_list.append(index)

                inside_blockquote = True
                continue

            elif line.endswith(BLOCKQUOTE_EXPANDABLE_END_DELIM) and inside_blockquote:
                if line.startswith(BLOCKQUOTE_DELIM):
                    line = line[len(BLOCKQUOTE_DELIM) + (1 if line.startswith(f"{BLOCKQUOTE_DELIM} ") else 0) :]

                delim_stripped_line = line[:-len(BLOCKQUOTE_EXPANDABLE_END_DELIM)]

                parsed_line = (
                    html.escape(delim_stripped_line) if strict else delim_stripped_line
                )

                to_quote_list.append((index, parsed_line))
                html_escaped_list.append(index)

                inside_blockquote = False

                create_blockquote(expandable=True)

            if inside_blockquote:
                parsed_line = line[len(BLOCKQUOTE_DELIM) + (1 if line.startswith(f"{BLOCKQUOTE_DELIM} ") else 0) :]
                parsed_line = html.escape(parsed_line) if strict else parsed_line
                to_quote_list.append((index, parsed_line))
                html_escaped_list.append(index)

        # Handle Single line/Continued Quote
        for index, line in enumerate(text_lines):
            if line is None:
                continue

            if line.startswith(BLOCKQUOTE_DELIM):
                delim_stripped_line = line[len(BLOCKQUOTE_DELIM) + (1 if line.startswith(f"{BLOCKQUOTE_DELIM} ") else 0) :]
                parsed_line = (
                    html.escape(delim_stripped_line) if strict else delim_stripped_line
                )

                to_quote_list.append((index, parsed_line))
                html_escaped_list.append(index)

            elif len(to_quote_list) > 0:
                create_blockquote()
        else:
            create_blockquote()

        if strict:
            for idx, line in enumerate(text_lines):
                if idx not in html_escaped_list:
                    text_lines[idx] = html.escape(line)

        return "\n".join(
            [valid_line for valid_line in text_lines if valid_line is not None]
        )

    def parse(self, text: str, strict: bool = False):
        text = self.escape_and_create_quotes(text, strict=strict)
        delims = set()
        is_fixed_width = False

        for i, match in enumerate(re.finditer(MARKDOWN_RE, text)):
            start, _ = match.span()
            delim, is_emoji, text_url, url = match.groups()
            full = match.group(0)

            if delim in FIXED_WIDTH_DELIMS:
                is_fixed_width = not is_fixed_width

            if is_fixed_width and delim not in FIXED_WIDTH_DELIMS:
                continue

            if not is_emoji and text_url:
                text = replace_once(text, full, URL_MARKUP.format(url, text_url), start)
                continue

            if is_emoji:
                emoji = text_url
                emoji_id = url.lstrip("tg://emoji?id=")
                text = replace_once(text, full, EMOJI_MARKUP.format(emoji_id, emoji), start)
                continue

            if delim == BOLD_DELIM:
                tag = "b"
            elif delim == ITALIC_DELIM:
                tag = "i"
            elif delim == UNDERLINE_DELIM:
                tag = "u"
            elif delim == STRIKE_DELIM:
                tag = "s"
            elif delim == CODE_DELIM:
                tag = "code"
            elif delim == PRE_DELIM:
                tag = "pre"
            elif delim == SPOILER_DELIM:
                tag = "spoiler"
            else:
                continue

            if delim not in delims:
                delims.add(delim)
                tag = OPENING_TAG.format(tag)
            else:
                delims.remove(delim)
                tag = CLOSING_TAG.format(tag)

            if delim == PRE_DELIM and delim in delims:
                delim_and_language = text[text.find(PRE_DELIM):].split("\n")[0]
                language = delim_and_language[len(PRE_DELIM):]
                text = replace_once(text, delim_and_language, f'<pre language="{language}">', start)
                continue

            text = replace_once(text, delim, tag, start)

        return HTML.parse(text)

    @staticmethod
    def unparse(text: str, entities: list):
        text = add_surrogates(text)
        entities_offsets = []

        for entity in entities:
            entity_type = entity.type
            start = entity.offset
            end = start + entity.length

            if entity_type == TLEntityType.BOLD:
                start_tag = end_tag = BOLD_DELIM
            elif entity_type == TLEntityType.ITALIC:
                start_tag = end_tag = ITALIC_DELIM
            elif entity_type == TLEntityType.UNDERLINE:
                start_tag = end_tag = UNDERLINE_DELIM
            elif entity_type == TLEntityType.STRIKETHROUGH:
                start_tag = end_tag = STRIKE_DELIM
            elif entity_type == TLEntityType.CODE:
                start_tag = end_tag = CODE_DELIM
            elif entity_type == TLEntityType.PRE:
                language = getattr(entity, "language", "") or ""
                start_tag = f"{PRE_DELIM}{language}\n"
                end_tag = f"\n{PRE_DELIM}"
            elif entity_type == TLEntityType.BLOCKQUOTE:
                start_tag = BLOCKQUOTE_DELIM + " "
                end_tag = ""
                blockquote_text = text[start:end]
                lines = blockquote_text.split("\n")
                last_length = 0
                for line in lines:
                    if len(line) == 0 and last_length == end:
                        continue
                    start_offset = start+last_length
                    last_length = last_length+len(line)
                    end_offset = start_offset+last_length
                    entities_offsets.append((start_tag, start_offset,))
                    entities_offsets.append((end_tag, end_offset,))
                    last_length = last_length+1
                continue
            elif entity_type == TLEntityType.SPOILER:
                start_tag = end_tag = SPOILER_DELIM
            elif entity_type == TLEntityType.TEXT_LINK:
                url = entity.url
                start_tag = "["
                end_tag = f"]({url})"
            elif entity_type == TLEntityType.CUSTOM_EMOJI:
                emoji_id = entity.custom_emoji_id
                start_tag = "!["
                end_tag = f"](tg://emoji?id={emoji_id})"
            else:
                continue

            entities_offsets.append((start_tag, start,))
            entities_offsets.append((end_tag, end,))

        entities_offsets = map(
            lambda x: x[1],
            sorted(
                enumerate(entities_offsets),
                key=lambda x: (x[1][1], x[0]),
                reverse=True
            )
        )

        for entity, offset in entities_offsets:
            text = text[:offset] + entity + text[offset:]

        return remove_surrogates(text)
##############################  END Markdown & HTML parsers   ##############################


class Callback(dynamic_proxy(Utilities.Callback)):
    def __init__(self, fn: Callable[[Any], None], *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self, arg):
        self._fn(arg, *self._args, **self._kwargs)


class PluginInfo:
    is_cactuslib_plugin: bool

    def __init__(self, lib, plugin: BasePlugin, is_cactuslib_plugin: bool = False):
        self.lib = lib
        self.plugin = plugin
        self.is_cactuslib_plugin = is_cactuslib_plugin
    
    def format_in_list(self, rnd: str, offset: int) -> str:
        P = self.plugin
        L = self.lib
        plugin_format = "{emoji} <a href='{toggle_uri}'>({toggle})</a> [{version}] <b>{name}</b> (<code>{id}</code>){commands}"
        return plugin_format.format(
            emoji="🥏" if P.enabled else "🚫",
            toggle_uri=L.utils.Uri.create(L, "setPluginEnabled", id=P.id, rnd=rnd, isAllList="true", offset=offset),
            toggle=L.string("enable" if not P.enabled else "disable"),
            id=P.id,
            name=("<a href='" + L.utils.Uri.create(L, "openPluginHelp", id=P.id, rnd=rnd) + f"'>{P.name}</a>"),
            version=P.version or '-',
            commands=(" | " + " • ".join([
                f"<code>{X[0]}</code>" + ((f" (<code>" + '</code> - <code>'.join(X[1].__aliases__) + "</code>)") if X[1].__aliases__ else "")
                for X in getattr(P, "_commands", [])
                if getattr(X[1], "__enabled__", None) is None or (
                    isinstance(X[1].__enabled__, bool)
                    and X[1].__enabled__
                ) or (
                    isinstance(X[1].__enabled__, str)
                    and P.get_setting(X[1].__enabled__, True)
                )
            ])) if self.is_cactuslib_plugin else "",
        )

    def export_settings(self):
        # PLEASE DONT USE THIS IN ANY PLUGIN
        all_settings = get_private_field(PluginsController.getInstance(), "preferences").getAll()
        keys = [
            m.group(1) for skey in list(all_settings.keySet().toArray())
            if (m := re.match(re.compile(f"plugin_setting_{self.plugin.id}_(.*)"), skey))
        ]

        return {
            key: all_settings.get(f"plugin_setting_{self.plugin.id}_{key}")
            for key in keys
        }
        # PLEASE DONT USE THIS IN ANY PLUGIN
    
    def get_file_path(self):
        return PluginsController.getInstance().getPluginPath(self.plugin.id)
    
    def export(self, with_data: bool = True):
        file_content = None
        with open(self.get_file_path(), "rb") as f:
            file_content = f.read()
        
        return {
            "file_content": CactusUtils.compress_and_encode(file_content),
            "settings": self.export_settings() if with_data else None,
            "data": self.export_data() if with_data else None,
            "plugin_meta": {
                "id": self.plugin.id,
                "name": self.plugin.name,
                "version": self.plugin.version,
                "enabled": self.plugin.enabled,
            }
        }

    def export_data(self):
        if not self.is_cactuslib_plugin:
            return None

        return getattr(self.plugin, "export_data", lambda: None)()


class CactusUtils:
    _get_setting = None
    _plugins = None

    Callback = Callback

    @dataclass
    class Command:
        command: str
        args: List[str]
        raw_args: Optional[str]
        text: str
        account: int

        params: Any

    class FileSystem:
        File = File

        @classmethod
        def basedir(cls):
            return ApplicationLoader.getFilesDirFixed()
        
        @classmethod
        def cachedir(cls):
            return ApplicationLoader.applicationContext.getExternalCacheDir()

        @classmethod
        def tempdir(cls):
            _dir = File(cls.cachedir(), "cactuslib_temp_files")
            if not _dir.exists():
                _dir.mkdirs()
            return _dir

        @classmethod
        def get_file_content(cls, file_path, mode: str = "rb"):
            with open(file_path, mode) as f:
                return f.read()
        
        @classmethod
        def get_temp_file_content(
            cls, filename: str, mode: str = "rb", delete_after: int = 0
        ):
            file_path = File(cls.tempdir(), filename).getAbsolutePath()
            content = cls.get_file_content(file_path, mode)
            if delete_after > 0:
                threading.Timer(delete_after, lambda: os.remove(file_path)).start()
            return content

        @classmethod
        def write_file(cls, file_path, content, mode: str = "wb"):
            with open(file_path, mode) as file:
                file.write(content)
            
            return file_path
        
        @classmethod
        def write_temp_file(cls, filename: str, content, mode="wb", delete_after: int = 0):
            path = cls.write_file(File(cls.tempdir(), filename).getAbsolutePath(), content, mode)
            if delete_after > 0:
                threading.Timer(delete_after, lambda: os.remove(path)).start()
            
            return path
        
        @classmethod
        def delete_file_after(cls, file_path, seconds: int = 0):
            if os.path.exists(file_path):
                if seconds > 0:
                    threading.Timer(seconds, lambda: os.remove(file_path)).start()
                    return
                
                os.remove(file_path)

    @classmethod
    def compress_and_encode(cls, data: bytes, level: int = 7) -> str:
        if not data:
            return ""
        compressed_data = zlib.compress(data, level=level)
        encoded_data = base64.b64encode(compressed_data).decode('utf-8')
        return encoded_data

    @staticmethod
    def decode_and_decompress(encoded_data: bytes):
        if not encoded_data:
            return b""
        decoded_data = base64.b64decode(encoded_data)
        decompressed_data = zlib.decompress(decoded_data)
        return decompressed_data

    @staticmethod
    def pluralization_string(number: int, words: List[str]):
        """
        Returns a pluralized string based on the given number.

        Args:
            number (int): The number to determine the plural form.
            words (list[str]): A list of words representing the singular, dual, and plural forms.

        Returns:
            str: The pluralized string based on the given number.

        Examples:
            >>> num = 5
            >>> pluralization_string(num, ["жизнь", "жизни", "жизней"])
            >>> pluralization_string(num, ["рубль", "рубля", "рублей"])
            >>> pluralization_string(num, ["ручка", "ручки", "ручек"])
            >>> pluralization_string(num, ["апельсин", "апельсина", "апельсинов"])
        """
        if number % 10 == 1 and number % 100 != 11:
            return f"{number} {words[0]}"
        elif 2 <= number % 10 <= 4 and (number % 100 < 10 or number % 100 >= 20):
            return f"{number} {words[1]}"
        else:
            return f"{number} {words[2]}"

    @classmethod
    def initialize_plugin(cls, plugin: BasePlugin):
        cls._plugins = [plugin] if cls._plugins is None else cls._plugins + [plugin]
        
        if "validation" in plugin.id:
            plugin.on_plugin_unload()

    @classmethod
    def unload_plugin(cls, plugin: BasePlugin):
        if plugin not in (cls._plugins or []):
            return
        
        cls._plugins.remove(plugin)

    @staticmethod
    def escape_html(text: str):
        return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    
    @staticmethod
    def show_error(message: str):
        BulletinHelper.show_error(message)
    
    @staticmethod
    def show_info(message: str):
        BulletinHelper.show_info(message)
    
    @staticmethod
    def copy_to_clipboard(text: str):
        if AndroidUtilities.addToClipboard(text):
            BulletinHelper.show_copied_to_clipboard()

    @classmethod
    def prefix(cls):
        return cls._get_setting("prefix", ".") if cls._get_setting is not None else "."

    @classmethod
    def get_locale(cls):
        return (cls._get_setting("language", "") or Locale.getDefault().getLanguage()) if cls._get_setting is not None else Locale.getDefault().getLanguage()

    @staticmethod
    def log(message: str, level: str = "INFO", __id__: Optional[str] = __id__):
        """
        Logs a message to logcat with the specified level.

        Args:
            message (str): The message to log.
            level (str): The log level (e.g., "DEBUG", "INFO", "WARN", "ERROR" or custom lvl).
        """
        
        logcat(f"[{level}] [{__id__}] " + message.replace("\n", "<CNL>"))
    
    @staticmethod
    def debug(message: str, __id__: Optional[str] = __id__):
        """Logs a debug message to logcat."""
        CactusUtils.log(message, "DEBUG", __id__)

    @staticmethod
    def error(message: str, __id__: Optional[str] = __id__):
        """Logs an error message to logcat."""
        CactusUtils.log(message, "ERROR", __id__)

    @staticmethod
    def info(message: str, __id__: Optional[str] = __id__):
        """Logs an info message to logcat."""
        CactusUtils.log(message, "INFO", __id__)

    @staticmethod
    def warn(message: str, __id__: Optional[str] = __id__):
        """Logs a warning message to logcat."""
        CactusUtils.log(message, "WARN", __id__)

    @staticmethod
    def runtime_exec(command: List[str], return_list_lines: bool = False, raise_errors: bool = True) -> Union[List[str], str]:
        result = []
        process = None
        reader = None
        try:
            process = Runtime.getRuntime().exec(command)
            reader = BufferedReader(InputStreamReader(process.getInputStream()))

            line = reader.readLine()
            while line is not None:
                result.append(line.strip())
                line = reader.readLine()
            
            try:
                process.waitFor()
            except InterruptedException as ie:
                CactusUtils.error(f"Runtime exec process ({command}) waitFor interrupted: {ie}")
                threading.currentThread().interrupt()
        except IOException as e:
            CactusUtils.error(f"[IOException:RuntimeExec({command})] reading exec process: {e}\n{traceback.format_exc()}")
            if raise_errors:
                raise e
        except Exception as e:
            CactusUtils.error(f"[RuntimeExec({command})] General error fetching logcat: {e}\n{traceback.format_exc()}")
            if raise_errors:
                raise e
        finally:
            if reader:
                try:
                    reader.close()
                except IOException as e:
                    CactusUtils.error(f"[IOException:RuntimeExec({command})] Error closing runtime exec reader: {e}")
            if process:
                process.destroy()

        return result if return_list_lines else "\n".join(result)

    @staticmethod
    def get_logs(__id__: Optional[str] = None, time: Optional[int] = None, lvl: Optional[str] = None, as_list: bool = False):
        """
        Returns a list of logs from logcat by __id__ and time (in seconds).

        Args:
            __id__ (Optional[str]): The id of the plugin
            time (Optional[int]): The time in seconds to get logs from
        """
        command = ["logcat", "-d", "-v", "time"] + (
            [
                "-T",
                String.format(
                    Locale.US,
                    "%.3f",
                    Double((JavaSystem.currentTimeMillis() - (time * 1000)) / 1000.0)
                )
            ] if time else []
        )


        result = [
            re.sub(r" D/\[PyObject]\((?:.+[0-9])\):", "", line.replace("<CNL>", "\n").replace(" [callAttrThrows]", ""))
            if __id__ or lvl
            else line.replace("<CNL>", "\n")
            for line in CactusUtils.runtime_exec(command, return_list_lines=True)
            if (
                __id__ is None or f"[{__id__}]" in line
            ) and (
                lvl is None or f"[{lvl}]" in line
            )
        ]

        CactusUtils.debug(f"Got logs with {__id__=}, {time=}s, {lvl=}")
    
        return result if as_list else "\n".join(result)

    @classmethod
    def parse_message(cls, text: str, parse_mode: str) -> Dict[str, Any]:
        try:
            result = (Markdown() if parse_mode == "MARKDOWN" else HTML()).parse(text)
            
            return {
                "message": result["message"],
                "entities": [i.to_tlrpc_object() for i in result["entities"]]
            }
        except SyntaxError as e:
            cls.error(f"Markdown parsing error: {e}")
            raise e
        except Exception as e:
            cls.error(f"An unexpected error occurred: {e}")
            raise e
    
    @classmethod
    def array_list(cls, *args):
        _l = ArrayList()

        if len(args) == 1 and isinstance(args[0], list):
            for arg in args[0]:
                _l.add(arg)
        else:
            for arg in args:
                _l.add(arg)
        
        return _l

    @classmethod
    def send_message(cls, peer: int, text: str, parse_message: bool = True, parse_mode: str = "MARKDOWN", **kwargs):
        return send_message(
            {
                "peer": peer,
                **(
                    cls.parse_message(text, parse_mode)
                    if parse_message
                    else {"message": text}
                ),
                **kwargs
            }
        )

    @classmethod
    def open_plugin_settings(cls, plugin_id: str):
        def _open_settings():
            try:
                get_last_fragment().presentFragment(PluginSettingsActivity(PluginsController.getInstance().plugins.get(plugin_id)))
            except:
                cls.error(f"Failed to open plugin settings. {traceback.format_exc()}")
        
        run_on_ui_thread(_open_settings)

    @dataclass
    class Uri:
        plugin_id: str
        command: str
        kwargs: Dict[str, str]

        @classmethod
        def create(cls, plugin, command: str, **kwargs):
            return cls(plugin.id, command, kwargs).string()
        
        def string(self):
            return f"tg://cactus/{self.plugin_id}/{self.command}?{urlencode(self.kwargs)}"

    @classmethod
    def edit_message(cls, message_object: MessageObject, text: str, parse_message: bool = True, parse_mode: str = "MARKDOWN", **kwargs): 
        entities = ArrayList()
        if parse_message:
            parsed = cls.parse_message(text, parse_mode)
            text = parsed["message"]
            entities = cls.array_list(parsed["entities"])
        
        return get_send_messages_helper().editMessage(message_object, text, False, kwargs.get("fragment", None), entities, kwargs.get("scheduleDate", 0))

    class CactusModule(BasePlugin):
        """
        Base class for plugins with CactusUtils and other features
        """

        utils: "CactusUtils"
        __min_lib_version__: str = None

        def __init__(self):
            super().__init__()
            self.utils = CactusUtils()

        strings: Dict[str, Dict[str, str]]

        def export_data(self) -> Dict[str, Any]:
            return {}
        
        def import_data(self, data):
            pass

        def on_plugin_load(self):
            self.utils = CactusUtils()

            if self.__min_lib_version__ and tuple(map(int, self.__min_lib_version__.split("."))) > tuple(map(int, __version__.split("."))):
                raise Exception(f"Plugin requires cactuslib version {self.__min_lib_version__} or higher, but {__version__} is installed")

            self.debug("Initializing plugin...")
            self._commands = self.__search_commands()
            self._uri_handlers = self.__search_uri_handlers()
            self.debug("Commands found: %s" % self._commands)
            self.debug("URI handlers found: %s" % self._uri_handlers)
            if self._commands:
                self.add_on_send_message_hook(priority = -1)
            
            self.utils.initialize_plugin(self)

            self.debug("Finished zero-level initializing plugin.")

        def on_plugin_unload(self):
            self.info("Unloading plugin...")
            self.remove_hook("on_send_message")
            self.utils.unload_plugin(self)

        def open_plugin_settings(self):
            self.utils.open_plugin_settings(self.id)

        @final
        def __search_commands(self) -> List[Tuple[str, Any, str]]:
            return [
                (y.__cmd__, y, x)
                for x, y in inspect.getmembers(self, predicate=inspect.ismethod)
                if not x.startswith("_") and getattr(y, "__is_command__", None) is True
            ]
        
        @final
        def __search_uri_handlers(self) -> List[Tuple[str, Any, str]]:
            return [
                (y.__uri__, y, x)
                for x, y in inspect.getmembers(self, predicate=inspect.ismethod)
                if not x.startswith("_") and getattr(y, "__is_uri_handler__", None) is True
            ]

        @final
        def lstrings(self) -> Dict[str, str]:
            locale_dict: Dict[str, str] = self.strings.get(self.utils.get_locale(), self.strings)
            if "en" in locale_dict:
                locale_dict = locale_dict["en"]
            
            return locale_dict

        @final
        def string(self, key: str, *args, default: Optional[str] = None, locale: str = None, **kwargs) -> str:
            if key is None:
                return default.format(*args, **kwargs)
            
            base_strings = self.strings.get("en", self.strings)

            locale_dict: Dict[str, str] = self.strings.get(self.utils.get_locale() if not locale else locale, self.strings)
            if "en" in locale_dict:
                locale_dict = locale_dict["en"]
            
            string = (locale_dict.get(key, base_strings.get(key, default)) or default)
            if args or kwargs:
                string = string.format(*args, **kwargs)
            
            return string

        @final
        def log(self, message: str, level: str = "INFO"):
            """
            Logs a message to logcat with the specified level.

            Args:
                message (str): The message to log.
                level (str): The log level (e.g., "DEBUG", "INFO", "WARN", "ERROR" or custom lvl).
            """
            CactusUtils.log(message, level, self.id)
        
        @final
        def debug(self, message: str):
            """Logs a debug message to logcat."""
            CactusUtils.debug(message, self.id)

        @final
        def error(self, message: str):
            """Logs an error message to logcat."""
            CactusUtils.error(message, self.id)

        @final
        def info(self, message: str):
            """Logs an info message to logcat."""
            CactusUtils.info(message, self.id)

        @final
        def warn(self, message: str):
            """Logs a warning message to logcat."""
            CactusUtils.warn(message, self.id)

        @final
        def on_send_message_hook(self, account, params):
            prefix = self.utils.prefix()
            if (
                not params or not params.message
                or not isinstance(params.message, str)
                or not params.message.startswith(prefix)
            ):
                return HookResult()

            text = params.message.strip()
        
            for command, func, hook_method_name in self._commands:
                if (
                    isinstance(func.__enabled__, bool)
                    and not func.__enabled__
                ) or (
                    isinstance(func.__enabled__, str)
                    and not func.__self__.get_setting(func.__enabled__, True)
                ):
                    continue

                aliases = func.__aliases__ or []
                s_aliases = "" if not aliases else "|" + "|".join(aliases)
                m = re.match(re.compile(f"^[{prefix}]({command}{s_aliases})(?:\s+(.*))?$", re.S), text)
                if not m:
                    continue

                try:
                    args = shlex.split(m.group(2)) if m.group(2) else []
                except ValueError:
                    args = [m.group(2)]

                try:
                    command_obj = self.utils.Command(
                        command=m.group(1),
                        args=args,
                        raw_args=m.group(2),
                        text=text,
                        account=account,
                        params=params
                    )

                    return func(command_obj)
                except Exception as e:
                    formatted = traceback.format_exc()
                    self.error(f"Message hook error: [{str(e)}] {formatted}")
                    self.answer(params, f"🚫 <b>Error</b> while executing <b>message hook <i>{hook_method_name}</i></b>:\n```python\n{self.utils.escape_html(formatted[:4000])}```🔰 *Plugin {self.name}* (`{prefix}{command}`)")
                    return HookResult()

        @final
        def on_uri_command_hook(self, cmd: str, kwargs: Dict[str, Any]):
            for command, func, hook_method_name in self._uri_handlers:
                if cmd == command:
                    try:
                        return func(**kwargs)
                    except Exception as e:
                        self.error(f"URI hook {hook_method_name} error: [{str(e)}] {traceback.format_exc()}")
                        self.utils.show_error(f"[URIHook:{hook_method_name}] Error, see log for details.")
                        return

        @final
        def answer(self, params, text: str, *, parse_message: bool = True, parse_mode: str = "MARKDOWN", **kwargs):
            """
            TODO: сделать разделение если больше 4096 символов
            """

            X = self.utils.parse_message(text, parse_mode) if parse_message else {"message": text, "entities": kwargs.get("entities", params.entities)}

            return send_message(
                {
                    "peer": params.peer,
                    "replyToMsg": params.replyToMsg,
                    "replyToTopMsg": params.replyToTopMsg,
                    **X,
                    **kwargs
                }
            )
        
        @final
        def edit_message(self, params, text: str, parse_message: bool = True, parse_mode: str = "MARKDOWN", **kwargs):
            if parse_message:
                parsed = self.utils.parse_message(text, parse_mode)
                params.message = parsed["message"]
                params.entities = self.utils.array_list(parsed["entities"])
            else:
                params.message = text
            
            for k, v in kwargs.items():
                setattr(params, k, v)

            return HookResult(HookStrategy.MODIFY, params=params)
        
        @final
        def answer_file(self, peer: int, path: str, caption: Optional[str] = None, *, parse_message: bool = True, parse_mode: str = "MARKDOWN", **kwargs):
            """
            Sends a file with path and caption

            Additional kwargs:
            - `mime` (`str`): MIME type of the file (default: `text/plain`)
            - `replyToMsg`: Message to reply to
            - `replyToTopMsg`: top message to reply to (thread id)
            - `storyItem` (`TL_stories.StoryItem`): Story item
            - `quote` (`ChatActivity.ReplyQuote`): Quote
            - `notify` (`bool`): Send notification
            - `editingMessageObject` (`MessageObject`): Message to edit/add file
            - `scheduleDate` (`int`): Schedule date
            - `quickReplyShortcut` (`str`): Quick reply shortcut
            - `quickReplyShortcutId` (`int`): Quick reply shortcut ID
            - `effect_id` (`int`): Effect ID
            - `invertMedia` (`bool`): Invert media
            - `payStars` (`int`): Pay stars
            - `monoForumPeerId` (`int`): Mono forum peer ID
            """
            if caption and parse_message:
                parsed = self.utils.parse_message(caption, parse_mode)
                caption = parsed["message"]
                kwargs["entities"] = self.utils.array_list(parsed["entities"])
            
            [method] = [m for m in SendMessagesHelper.getClass().getDeclaredMethods() if m.getName() == "prepareSendingDocumentInternal"]
            method.setAccessible(True)
            
            method.invoke(
                None,
                get_account_instance(), path, path, None, kwargs.get("mime", "text/plain"),
                peer, kwargs.get("replyToMsg", None), kwargs.get("replyToTopMsg", None),
                kwargs.get("storyItem", None), kwargs.get("quote", None), kwargs.get("entities", None),
                kwargs.get("editingMessageObject", None), jarray(jlong)([0]), True, caption, kwargs.get("notify", True),
                jint(kwargs.get("scheduleDate", 0)), kwargs.get("docType", jarray(Integer)([0])), True,
                kwargs.get("quickReplyShortcut", None), jint(kwargs.get("quickReplyShortcutId", 0)),
                kwargs.get("effect_id", 0), kwargs.get("invertMedia", False), kwargs.get("payStars", 0),
                kwargs.get("monoForumPeerId", 0)
            )

        @final
        def answer_photo(self, params, path: str, caption: Optional[str] = None, *, parse_message: bool = True, edit_params: bool = False, **kwargs):
            photo = get_send_messages_helper().generatePhotoSizes(path, None)
            if not photo:
                raise Exception("Failed to generate photo sizes")
            
            entities = ArrayList()
            if caption and parse_message:
                parsed = self.utils.parse_message(caption)
                caption = parsed["message"]
                entities = self.utils.array_list(parsed["entities"])
            
            if edit_params:
                params.photo = photo
                params.path = path

                params.caption = caption
                params.entities = entities

                for k, v in kwargs.items():
                    setattr(params, k, v)

                return HookResult(strategy=HookStrategy.MODIFY, params=params)
            else:
                send_message(
                    {
                        "peer": params.peer,
                        "replyToMsg": params.replyToMsg,
                        "replyToTopMsg": params.replyToTopMsg,
                        "caption": caption,
                        "entities": entities,
                        "path": path,
                        "photo": photo,
                        **kwargs
                    }
                )

    Plugin = CactusPlugin = CactusModule
    PluginInfo = PluginInfo

    class Telegram:
        @staticmethod
        def tlrpc_object(request_class, **kwargs):
            for k, v in kwargs.items():
                setattr(request_class, k, v)
            
            return request_class
            
        class SearchFilter(Enum):
            GIF = 'gif'
            MUSIC = 'music'
            CHAT_PHOTOS = 'chat_photos'
            PHOTOS = 'photos'
            URL = 'url'
            DOCUMENT = 'document'
            PHOTO_VIDEO = 'photo_video'
            PHOTO_VIDEO_DOCUMENT = 'photo_video_document'
            GEO = 'geo'
            PINNED = 'pinned'
            MY_MENTIONS = 'my_mentions'
            ROUND_VOICE = 'round_voice'
            CONTACTS = 'contacts'
            VOICE = 'voice'
            VIDEO = 'video'
            PHONE_CALLS = 'phone_calls'
            ROUND_VIDEO = 'round_video'
            EMPTY = 'empty'

            def to_TLRPC_object(self):
                camel_case = re.sub(r'_([a-z])', lambda match: match.group(1).upper(), self.value)
                camel_case = camel_case[0].upper() + camel_case[1:]
                return getattr(TLRPC, f"TL_inputMessagesFilter" + camel_case)()
    
        @classmethod
        def search_messages(
            cls,
            callback: Callable[[List[MessageObject], Any], None],
            dialog_id: int,
            query: Optional[str] = None,
            from_id: Optional[int] = None,
            offset_id: int = 0,
            limit: int = 20,
            reply_message_id: Optional[int] = None,
            top_message_id: Optional[int] = None,
            filter: SearchFilter = SearchFilter.EMPTY,
        ):
            def _convert_messages(result, error):
                if error:
                    callback(None, error)
                    return
                
                messages = []
                for i in range(result.messages.size()):
                    messages.append(MessageObject(get_account_instance().getCurrentAccount(), result.messages.get(i), False, False))
                
                callback(messages, None)
        
            req = cls.tlrpc_object(
                TLRPC.TL_messages_search(),
                peer=cls.input_peer(dialog_id),
                q=query,
                offset_id=offset_id,
                limit=limit,
                filter=filter.to_TLRPC_object(),
            )
            if from_id:
                req.from_id = cls.input_peer(from_id)
                req.flags |= 1
            if reply_message_id or top_message_id:
                req.top_msg_id = reply_message_id or top_message_id
                req.flags |= 2
            return get_connections_manager().sendRequest(req, RequestCallback(_convert_messages))
    
        @staticmethod
        def get_user(user_id: int):
            return get_messages_controller().getUser(user_id)
        
        @staticmethod
        def peer(peer_id: int):
            return get_messages_controller().getPeer(peer_id)
        
        @staticmethod
        def input_peer(peer_id: int):
            return get_messages_controller().getInputPeer(peer_id)

        @staticmethod 
        def get_channel(callback: Callable[[Any, Any], None], channel_id: int) -> int:
            req = TLRPC.TL_channels_getChannels()
            input_channel = get_messages_controller().getInputChannel(channel_id)
            req.id.add(input_channel)
            return send_request(req, RequestCallback(callback))
            
        @staticmethod
        def get_chat(callback: Callable[[Any, Any], None], chat_id: int) -> int:
            req = TLRPC.TL_messages_getChats()
            input_chat = get_messages_controller().getInputChat(chat_id)
            req.id.add(input_chat)
            return send_request(req, RequestCallback(callback))
            
        @classmethod
        def create_input_location(cls, photo, size):
            return cls.tlrpc_object(
                TLRPC.TL_inputPhotoLocation(),
                id=photo.id,
                access_hash=photo.access_hash,
                file_reference=photo.file_reference,
                thumb_size=size.type,
            )
        
        @classmethod
        def create_peer_input_location(cls, chat, peer):
            return cls.tlrpc_object(
                TLRPC.TL_inputPeerPhotoFileLocation(),
                big=True,
                peer=cls.input_peer(peer),
                photo_id=chat.photo.photo
            )
            
        @classmethod
        def get_chat_thumbnail(cls, callback: Callable[[Any, Any], None], chat, peer) -> int:
            return send_request(
                cls.tlrpc_object(
                    TLRPC.TL_upload_getFile(),
                    location=cls.create_peer_input_location(chat, peer),
                    offset=0,
                    limit=1024*1024
                ),
                RequestCallback(callback)
            )
        
        @classmethod
        def get_user_photos(cls, callback: Callable[[Any, Any], None], user_id: int, limit: int = 1) -> int:
            return send_request(
                cls.tlrpc_object(
                    TLRPC.TL_photos_getUserPhotos(),
                    user_id=cls.input_peer(user_id),
                    limit=limit
                ),
                RequestCallback(callback)
            )

        @classmethod
        def delete_messages(cls, messages: List[int], chat_id: int, topic_id: int = 0):
            return get_messages_controller().deleteMessages(CactusUtils.array_list([jint(i) for i in messages]), None, None, chat_id, topic_id, True, 0)

        @classmethod
        def get_sticker_set_by_short_name(cls, callback: Callable[[Any, Any], None], short_name: str) -> int:
            return send_request(
                cls.tlrpc_object(
                    TLRPC.TL_messages_getStickerSet(),
                    stickerset=cls.tlrpc_object(
                        TLRPC.TL_inputStickerSetShortName(),
                        short_name=short_name
                    )
                ),
                RequestCallback(callback)
            )

    @classmethod
    def get_message_by_rnd_in_current_chat(cls, rnd: str, fn: Callable[[MessageObject, Any], None]):
        fragment = get_last_fragment()
        if fragment.__class__.__name__ == "ChatActivity":
            def _search_message_callback(response, error):
                if error or not response:
                    cls.error(error or "...")
                    cls.show_error((error or "...")[:30])
                    return
                
                fn(response[0], fragment)

            cls.Telegram.search_messages(
                callback=_search_message_callback,
                dialog_id=get_private_field(fragment, "dialog_id"),
                query=rnd,
                limit=21,
                top_message_id=get_private_field(fragment, "threadMessageId"),
            )
        else:
            cls.warn(f"[{rnd}] You are not in a chat!...")
    
    @contextmanager
    def SpinnerAlertDialog(self, text: Optional[str] = None):
        spinner_dialog_builder = None
        def _show_dialog():
            nonlocal spinner_dialog_builder
            act = get_last_fragment().getParentActivity()
            if not act:
                return
            
            spinner_dialog_builder = AlertDialogBuilder(act, AlertDialogBuilder.ALERT_TYPE_SPINNER)
            spinner_dialog_builder.set_cancelable(False)
            if text and hasattr(spinner_dialog_builder, "set_text"):
                try:
                    spinner_dialog_builder.set_text(text)
                except Exception:
                    pass
            spinner_dialog_builder.show()

        def hide_spinner():
            nonlocal spinner_dialog_builder
            if spinner_dialog_builder:
                try:
                    spinner_dialog_builder.dismiss()
                except Exception:
                    pass
                spinner_dialog_builder = None

        try:
            run_on_ui_thread(_show_dialog)
            yield spinner_dialog_builder
        except:
            run_on_ui_thread(hide_spinner())
            raise
        finally:
            run_on_ui_thread(hide_spinner())


def command(
    command: Optional[str] = None, *,
    aliases: Optional[List[str]] = None,
    doc: Optional[str] = None,
    enabled: Optional[Union[str, bool]] = None
):
    """
    Decorator for commands

    Args:
        command (str): The command
        aliases (List[str]): A list of aliases for the command
        doc (str): String-key in `strings` for command description
        enabled (str/bool): Setting-key or boolean for enabling the command
    """
    def decorator(func):
        func.__is_command__ = True
        func.__aliases__ = aliases
        func.__cdoc__ = doc
        func.__enabled__ = enabled
        func.__cmd__ = command or func.__name__

        return func
    return decorator


def uri(uri: str):
    """
    Decorator for URIs

    Args:
        uri (str): The URI
    """
    def decorator(func):
        func.__is_uri_handler__ = True
        func.__uri__ = uri
        return func
    return decorator


class CactusLib(CactusUtils.CactusModule):
    strings = {
        "en": {
            "settings_command_prefix_label": "Command prefix",
            "settings_info_header": "Info (Help)",
            "logs": "🌵 <b>[{lvl}] Logs</b> with PID <code>{id}</code>\n{contains}\n<pre lang=python>...\n{last_logs}\n</pre>",
            "contains": "ℹ️ Contains: `{}`",
            "eval_error": "❌ *Error*:\n```python\n{}``````python\n{}\n```",
            "eval_result": "✅ *Result*:\n```python\n{}``````python\n{}\n```",
            "eval_result_file": "🗞 *Result* in the txt-file ```python\n{}\n```",
            "plf_doc": "<plugin-id or plugin-name> - send plugin file",
            "cexport_doc": "- message-version of export",
            "no_logs": "❌ No logs found",
            "cactus_plugins": "🌵 <b>Installed plugins with using CactusLib</b> ({})\n<blockquote>{}</blockquote>\n",
            "other_plugins": "🎈 <b>Other plugins</b> ({})\n<blockquote>{}</blockquote>\n",
            "next_page": "<a href='{}'>⏩ Next page</a>",
            "prev_page": "<a href='{}'>⏪ Previous page</a>",
            "plugin_info": "{emoji} <b>{name}</b> ( <code>{id}</code> )\n<blockquote>{doc}</blockquote>📶 <b>{version}</b> ({author})\n{toggle}{settings}{send_file}\n{commands}{all_list_uri}",
            "toggle_uri": "<a href=\"{}\">{} {}</a>\n",
            "get_file_uri": "<a href=\"{}\">📁 Get file</a>\n",
            "settings_uri": "<a href=\"{}\">⚙️ Settings</a>\n",
            "plugin_command_format": "{emoji} <code>{prefix}{command}</code> {doc}",
            "help_cmd": "[plugin-name / command / plugin-id] - Show plugin info or all plugins",
            "eval_cmd": "<python-code> - Run python code",
            "logs_cmd": "[lvl] [plugin-id] [time(s)] [-c \"find bla\"] - Show logs by level, plugin-id, time and contains string",
            "no_args": "❌ Where are the arguments themselves?",
            "prefix_must_be_one_char": "❌ Prefix must be one character",
            "prefix_set": "✅ New command prefix set: {}",
            "set_prefix_doc": "<prefix> - set new command prefix",
            "settings_commands_header": "Commands",
            "command_logger": "Command logger",
            "command_logger_subtext": "Enables logging of commands in the specified chat",
            "command_logger_chat_label": "Logger chat ID",
            "command_logger_chat": "Can be set by using the set_logger_chat command in the chat",
            "invalid_peer_id": "❌ Invalid chat ID (should be an integer)",
            "logger_chat_set": "✅ Logger chat ID set: {}",
            "set_logger_chat_cmd_doc": "[chat-id] - set chat-id for logging commands (recommended to use in the chat)",
            "settings_menu_item_header": "CactusLib's settings",
            "enabled": "enabled!", "enable": "ON", "toggle_d": "Disable",
            "disabled": "disabled!", "disable": "OFF", "toggle_e": "Enable",
            "plugin_not_found": "❌ Plugin <{}> not found", "all_list": "💠 All plugins",
            "settings_language_label": "Language for plugins (en/ru/...)",
            "settings_language_subtext": "Set empty to use the system language",
            "plugin_file_sent": "📁 <b>{plugin.name}</b> {version}",
            "exporting_plugins": "📤 <b>Export plugins with settings</b>\n<blockquote>Click on the <b>plugin name</b> to select</blockquote> <b>{add_all}  |  {clear}</b>\n<blockquote>{plugins}</blockquote>\n{export}",
            "add_all": "<a href='{}'>⏬ Add all</a>",
            "clear": "<a href='{}'>🗑 Clear</a>",
            "export": "<a href='{}'>🎯 <b>Export</b></a>",

            "select_plugins": "Select plugins",
            "select_plugins2": "Select plugins",
            "cancel": "Cancel",
            "import": "Import",
            "plugins": "Plugins",
            "selected_plugins": "{} selected",
            "processing": "Processing...",

            "import_alert_title": "Import {}",
            "import_info": "The file contains plugins with saved data.",
            "import_warning": "Note: You may lose the current plugins settings and data.",
            "import_progress": "Processed {}",
            "import_done": "Successfully imported {}!",

            "export_title": "Export Plugins",
            "export2": "Export",
            "export_progress": "Loaded {}",
            "export_info": "The file contains plugins with fully-saved data.",
            "export_warning": "The settings may contain confidential data.",
            "export_done": "Exported successfully!",

            "include_data_and_settings": "Include data and settings",
        },
        "ru": {
            "__doc__": "Библиотека Cactus с полноценным хелпом по командам и плагинам, безграничными возможностями для текстовых/uri команд, импорта/экспорта плагинов и многим другим!",
            "settings_command_prefix_label": "Префикс команды",
            "logs": "🌵 *[{lvl}] Логи* плагина с ID `{id}`\n{contains}\n```python\n...\n{last_logs}\n```",
            "contains": "ℹ️ Содержит: `{}`",
            "eval_error": "❌ *Ошибка*:\n```python\n{}``````python\n{}\n```",
            "eval_result": "✅ *Результат*:\n```python\n{}``````python\n{}\n```",
            "eval_result_file": "🗞 *Результат* находится в файле ```python\n{}\n```",
            "plf_doc": "<айди-плагина / имя-плагина> - получить код плагина в файле",
            "cexport_doc": "- меню экспорта в виде сообщения",
            "no_logs": "❌ Нет логов по вашему запросу",
            "settings_info_header": "Информация (Помощь)",
            "settings_uri": "<a href=\"{}\">⚙️ Настройки</a>\n",
            "get_file_uri": "<a href=\"{}\">📁 Выгрузить файл</a>\n",
            "cactus_plugins": "🌵 <b>Установленные плагины, использующие CactusLib</b> ({})\n<blockquote>{}</blockquote>\n",
            "other_plugins": "🎈 <b>Другие плагины</b> ({})\n<blockquote>{}</blockquote>\n",
            "next_page": "<a href='{}'>⏩ Следующая страница</a>",
            "prev_page": "<a href='{}'>⏪ Предыдущая страница</a>",
            "help_cmd": "[имя плагина / команда / id] - список плагинов или инфо о плагине и командах",
            "eval_cmd": "<python-код> - выполнить код и получить результат",
            "logs_cmd": "[lvl] [id плагина] [время(в секундах)] [-c \"find bla\"] - показать логи по уровню, id плагина и времени",
            "not_found": "❌ Ничего не найдено по запросу {}",
            "no_args": "❌ Где аргументы собственно?",
            "prefix_must_be_one_char": "❌ Префикс должен быть одним символом",
            "prefix_set": "✅ Новый префикс команд установлен: {}",
            "set_prefix_doc": "<префикс> - установить новый префикс для команд",
            "settings_commands_header": "Команды",
            "command_logger": "Логирование команд",
            "command_logger_subtext": "Включает логирование команд в указанный чат",
            "command_logger_chat_label": "ID Logger-чата",
            "command_logger_chat_subtext": "Можно установить командой set_logger_chat в нужном чате",
            "invalid_peer_id": "❌ Неверно указан ID чата (должно быть целым числом)",
            "logger_chat_set": "✅ ID Logger-чата установлен: {}",
            "set_logger_chat_cmd_doc": "[id чата] - установить id чата для логирования команд (рекомендуется использовать в самом чате)",
            "settings_menu_item_header": "Настройки CactusLib",
            "enabled": "включен!", "enable": "ВКЛ", "toggle_d": "Выключить",
            "disabled": "выключен!", "disable": "ВЫКЛ", "toggle_e": "Включить",
            "plugin_not_found": "❌ Плагин <{}> не найден", "all_list": "💠 Все плагины",
            "settings_language_label": "Язык для плагинов (локаль) (en/ru/...)",
            "settings_language_subtext": "Оставьте пустым, чтобы использовать язык системы",
            "exporting_plugins": "📤 <b>Экспорт плагинов с настройками</b>\n<blockquote>Нажмите на <b>имя плагина</b>, чтобы выбрать</blockquote><b>{add_all}  |  {clear}</b>\n<blockquote>{plugins}</blockquote>\n{export}",
            "add_all": "<a href='{}'>⏬ Добавить все</a>",
            "clear": "<a href='{}'>🗑 Очистить</a>",
            "export": "<a href='{}'>🎯 <b>Экспортировать</b></a>",
            
            "select_plugins": "Выбрать плагины",
            "select_plugins2": "Выберите плагины",
            "selected_plugins": "Выбрано {}",
            "cancel": "Отмена",
            "import": "Импорт",
            "plugins": "плагинов",
            "processing": "Загрузка...",
            
            "import_alert_title": "Импорт {}",
            "import_info": "В файле находятся плагины с полностью сохраненными данными.",
            "import_warning": "Вы можете потерять данные текущих плагинов.",
            "import_progress": "Импортировано {}",
            "import_done": "Успешно импортировано {}!",
            
            "export_title": "Экспорт плагинов",
            "export2": "Экспорт",
            "export_progress": "Загружено {}",
            "export_info": "Создаёт файл с текущими версиями плагинов и сохраненными данными.",
            "export_warning": "В настройках могут содержаться конфиденциальные данные.",
            "export_done": "Успешно!",

            "include_data_and_settings": "Включая данные и настройки",
        }
    }

    def _add_menu_items(self, lang: str = None):
        with suppress(Exception):
            self.remove_menu_item("cactuslib_settings")
            self.remove_menu_item("cactuslib_export")
        

        self.add_menu_item(MenuItemData(
            menu_type=MenuItemType.DRAWER_MENU,
            text=self.string("settings_menu_item_header") if not lang else self.string("settings_menu_item_header", locale=lang),
            icon="msg_settings_14",
            item_id="cactuslib_settings",
            priority=2,
            on_click=lambda ctx: self.open_plugin_settings()
        ))
        self.add_menu_item(MenuItemData(
            menu_type=MenuItemType.CHAT_ACTION_MENU,
            text=self.string("export_title") if not lang else self.string("export_title", locale=lang),
            icon="msg_filled_data_sent",
            item_id="cactuslib_export",
            priority=100,
            on_click=lambda ctx: run_on_ui_thread(
                lambda: self._open_export_plugins_alert(ctx)
            )
        ))

    def on_plugin_load(self):
        super().on_plugin_load()
        CactusUtils._get_setting = self.get_setting

        self._add_menu_items()

        self.__search_plugins()

        self.hook_method(
            [
                i for i in (
                    find_class("org.telegram.messenger.browser.Browser")
                    .getClass()
                    .getDeclaredMethods()
                )
                if repr(i) == (
                    "<java.lang.reflect.Method 'public static void org.telegram.messenger.browser.Browser.openUrl"
                    "(android.content.Context,android.net.Uri,boolean,boolean,boolean,org.telegram.messenger.browser.Browser$Progress"
                    ",java.lang.String,boolean,boolean,boolean)'>"
                )
            ][0], UriHandler(self), 0
        )
        self.hook_method(
            [
                i for i in (
                    find_class("org.telegram.messenger.AndroidUtilities")
                    .getClass()
                    .getDeclaredMethods()
                )
                if repr(i) == (
                    "<java.lang.reflect.Method 'public static boolean org.telegram.messenger.AndroidUtilities.openForView"
                    "(java.io.File,java.lang.String,java.lang.String,android.app.Activity,"
                    "org.telegram.ui.ActionBar.Theme$ResourcesProvider,boolean)'>"
                )
            ][0],
            DocumentHandler(self), 0
        )
    
    def execute_on_uri_command(self, plugin_id: str, command: str, kwargs: Dict[str, Any]):
        plugin: List[CactusUtils.Plugin] = [p for p in plugins_manager.PluginsManager._plugins.values() if p.id == plugin_id]
        if plugin:
            return plugin[0].on_uri_command_hook(command, kwargs)

    def __search_plugins(self):
        all_plugins = [p for p in plugins_manager.PluginsManager._plugins.values()]
        
        for plugin in all_plugins:
            plugin_utils = getattr(plugin, "utils", None)
            if plugin_utils and plugin_utils.__class__.__name__ == "CactusUtils" and plugin not in self.utils._plugins:
                self.utils.initialize_plugin(plugin)
    
    def create_settings(self):
        return [
            Header(text=self.string("settings_commands_header")),
            Input(
                key="prefix",
                text=self.string("settings_command_prefix_label"),
                default=".",
                icon="msg_limit_stories",
            ),
            Input(
                key="language",
                text=self.string("settings_language_label"),
                default=None,
                icon="",
                on_change=lambda lang: self._add_menu_items(lang),
                subtext=self.string("settings_language_subtext")
            ),
            Divider(),
        ]
    
    @uri("hello")
    def hello(self):
        self.utils.show_info("Hello, bro!")

    @uri("openPluginSettings")
    def uri_open_plugin_settings(self, id: str):
        self.utils.open_plugin_settings(id)

    @uri("setPluginEnabled")
    def uri_set_plugin_enabled(self, id: str, rnd: str, offset: int = 0, isAllList: str = "true"):
        if not id or not rnd:
            return
        
        def _fn(msg, fragment):
            if not msg:
                return
            
            self_id = get_user_config().getClientUserId()
            
            if msg.messageOwner.from_id.user_id == self_id and self._enable_plugin(id):
                text = self.help_query("" if isAllList == "true" else id, int(offset) )
                self.utils.edit_message(msg, text, parse_mode="HTML", fragment=fragment)
        
        self.utils.get_message_by_rnd_in_current_chat(rnd, _fn)
    
    def _enable_plugin(self, plugin_id: str) -> bool:
        plugin = ([
            p
            for p in plugins_manager.PluginsManager._plugins.values()
            if p.id == plugin_id
        ] or [None])[0]
        if plugin:
            _error = None
            def _callback(error: str):
                nonlocal _error
                if error:
                    _error = error
                    self.error(f"Error enabling plugin {plugin_id}: " + error)
                else:
                    _error = False
                    
            PluginsController.getInstance().setPluginEnabled(
                plugin.id,
                not plugin.enabled,
                self.utils.Callback(_callback)
            )

            while _error is None:
                time.sleep(0.1)
            
            if _error is False:
                self.utils.show_info(f"{plugin.name} " + self.string('enabled' if plugin.enabled else 'disabled'))
                return True
            else:
                self.utils.show_error(_error)
                return False
        else:
            self.utils.show_error(self.string("plugin_not_found", plugin_id))
            return False

    @uri("sendPluginFile")
    def uri_send_plugin_file(self, id: str, rnd: str, name: str, version: str = None):
        if not id or not rnd:
            return

        def _fn(msg, fragment):
            if not msg:
                return

            self_id = get_user_config().getClientUserId()

            if msg.messageOwner.from_id.user_id == self_id:
                with open(PluginsController.getInstance().getPluginPath(id), "rb") as f:
                    path = self.utils.FileSystem.write_temp_file(f"{name}_{version or '-'}.plugin", f.read())

                self.answer_file(msg.messageOwner.dialog_id, path, None, editingMessageObject=msg)
                self.utils.FileSystem.delete_file_after(path, 30)

        self.utils.get_message_by_rnd_in_current_chat(rnd, _fn)

    def help_query(self, query: Optional[str] = None, offset: int = 0, limit: int = 20):
        try:
            cactus_list = self.utils._plugins or []
            text = None
            prefix = self.utils.prefix()
            rnd = os.urandom(4).hex()

            other_plugins = sorted([
                p
                for p in plugins_manager.PluginsManager._plugins.values()
                if p not in self.utils._plugins
            ], key=lambda x: x.name.lower())

            if not query or query == "_":
                plugins_list = ([
                    PluginInfo(self, p, True)
                    for p in cactus_list
                ] + [
                    PluginInfo(self, p, False)
                    for p in other_plugins
                ])
                current_plugins_list = plugins_list[offset:offset + limit]

                text = ""
                cactus = [p for p in current_plugins_list if p.is_cactuslib_plugin]
                other = [p for p in current_plugins_list if not p.is_cactuslib_plugin]
                if cactus:
                    text += self.string("cactus_plugins", len(cactus), "\n".join([p.format_in_list(rnd, offset) for p in cactus]))
                if other:
                    text += self.string("other_plugins", len(other), "\n".join([p.format_in_list(rnd, offset) for p in other]))

                text += "\n"
                if offset > 0:
                    text += self.string("prev_page", self.utils.Uri.create(self, "openPluginHelp", id="_", rnd=rnd, offset=(offset - limit) if offset - limit >= 0 else 0))

                if offset + limit < len(plugins_list):
                    text += (" | " if offset > 0 else "") + self.string("next_page", self.utils.Uri.create(self, "openPluginHelp", id="_", rnd=rnd, offset=(offset + limit)))
                
            else:
                for plugin in cactus_list:
                    names = [
                        plugin.name.lower(),
                        plugin.id.lower(),
                    ]
                    for X in getattr(plugin, "_commands", []):
                        names.append(X[0].lower())
                        if X[1].__aliases__:
                            names.extend([i.lower() for i in X[1].__aliases__])

                    if query.lower() in names:
                        description = self.lstrings().get("__doc__", plugin.description)
                        emoji = random.choice(list("💊💉🪚🔩🏷📍💈🧿"))
                        text = self.string(
                            "plugin_info",
                            emoji="🌵" if plugin.enabled else "🚫", id=plugin.id,
                            name=plugin.name, version=plugin.version or '-', author=plugin.author,
                            doc=self.utils.escape_html(description),
                            toggle=self.string(
                                "toggle_uri",
                                self.utils.Uri.create(self, "setPluginEnabled", id=plugin.id, rnd=rnd, isAllList="false"),
                                "❇️" if not plugin.enabled else "❌",
                                self.string("toggle_" + ("d" if plugin.enabled else "e"))
                            ),
                            settings=self.string(
                                "settings_uri",
                                self.utils.Uri.create(self, "openPluginSettings", id=plugin.id)
                            ) if plugin.enabled and plugin.create_settings() else "",
                            send_file=self.string(
                                "get_file_uri",
                                self.utils.Uri.create(self, "sendPluginFile", id=plugin.id, rnd=rnd, name=plugin.name, version=plugin.version or '-')
                            ),
                            all_list_uri="<a href='" + self.utils.Uri.create(self, "openPluginHelp", id="_", rnd=rnd) + "'> " + self.string('all_list') + "</a>",
                            commands="\n".join([
                                self.string(
                                    "plugin_command_format",
                                    emoji=emoji if (
                                        isinstance(X[1].__enabled__, bool)
                                        and X[1].__enabled__
                                    ) or (
                                        isinstance(X[1].__enabled__, str)
                                        and self.get_setting(X[1].__enabled__, True)
                                    ) or not X[1].__enabled__ else "🚫",
                                    prefix=prefix,
                                    command=X[0],
                                    doc=self.utils.escape_html(plugin.string(X[1].__cdoc__, default=(X[1].__doc__ or "...").strip()).splitlines()[0])
                                ) + (
                                    (f" (<code>{prefix}" + f"</code> • <code>{prefix}".join(X[1].__aliases__) + "</code>)")
                                    if X[1].__aliases__
                                    else ""
                                )
                                for X in getattr(plugin, "_commands", [])
                            ]) + "\n\n"
                        )
                        break
                    
                
                if not text:
                    for plugin in other_plugins:
                        names = [
                            plugin.name.lower(),
                            plugin.id.lower(),
                        ]

                        if query.lower() in names:
                            text = self.string(
                                "plugin_info",
                                emoji="🎈" if plugin.enabled else "🚫", id=plugin.id,
                                name=plugin.name, version=plugin.version or '-', author=plugin.author,
                                doc=self.utils.escape_html(plugin.description),
                                commands="",
                                toggle=self.string(
                                    "toggle_uri",
                                    self.utils.Uri.create(self, "setPluginEnabled", id=plugin.id, rnd=rnd, isAllList="false", offset=offset),
                                    "❇️" if not plugin.enabled else "❌",
                                    self.string("toggle_" + ("d" if plugin.enabled else "e"))
                                ),
                                send_file=self.string(
                                    "get_file_uri",
                                    self.utils.Uri.create(self, "sendPluginFile", id=plugin.id, rnd=rnd, name=plugin.name, version=plugin.version or '-')
                                ),
                                settings=self.string(
                                    "settings_uri",
                                    self.utils.Uri.create(self, "openPluginSettings", id=plugin.id)
                                ) if plugin.enabled and plugin.create_settings() else "",
                                all_list_uri="<a href='" + self.utils.Uri.create(self, "openPluginHelp", id="_", rnd=rnd, offset=offset) + "'> " + self.string('all_list') + "</a>",
                            )
                            break
            
            return text
        except:
            self.error(traceback.format_exc())

    @uri("openPluginHelp")
    def uri_open_plugin_help(self, id: str, rnd: str, offset: int = 0):
        if id is None or not rnd:
            return
        
        def _fn(msg, fragment):
            if not msg:
                return
            
            if msg.messageOwner.from_id.user_id == get_user_config().getClientUserId():
                text = self.help_query(id, int(offset))
                self.utils.edit_message(msg, text, parse_mode="HTML", fragment=fragment)

        self.utils.get_message_by_rnd_in_current_chat(rnd, _fn)

    @command(doc="help_cmd")
    def chelp(self, command: CactusUtils.Command):
        args = command.raw_args
        text = self.help_query(args)
        
        if not text:
            self.utils.show_error(self.string("not_found", args))
            return HookResult(strategy=HookStrategy.CANCEL)

        return self.edit_message(command.params, text, parse_mode="HTML")

    @command(doc="logs_cmd")
    def logs(self, command: CactusUtils.Command):
        time = None
        lvl = None
        plugin_id = None
        contains = (None, None)

        if command.args:
            for index, arg in enumerate(command.args):
                if arg in LVLS:
                    lvl = arg
                elif arg.isdigit():
                    time = int(arg)
                elif arg == "-c":
                    contains = (index + 1, command.args[index+1])
                elif index != contains[0]:
                    plugin_id = arg

        logs = self.utils.get_logs(plugin_id, time, lvl, as_list=True)

        if contains[0]:
            logs = [log for log in logs if contains[1] in log]

        if not logs:
            BulletinHelper.show_error(self.string("no_logs"))
            return HookResult(strategy=HookStrategy.CANCEL)
        
        slogs = "\n".join(logs)

        lvl = lvl or "-"

        caption = self.string("logs", lvl=lvl, id=plugin_id, contains=self.string("contains", contains[1]) if contains[1] else "", last_logs=("\n".join([self.utils.escape_html(i) for i in logs[-7:]])))

        file_path = self.utils.FileSystem.write_temp_file((f"{plugin_id}_" if plugin_id else "") + (f"{lvl}_" if lvl != "-" else "") + f"logs.txt", slogs.encode("utf-8"))

        self.answer_file(command.params.peer, file_path, caption, replyToMsg=command.params.replyToMsg, replyToTopMsg=command.params.replyToTopMsg)
        self.utils.FileSystem.delete_file_after(file_path, 15)

        return HookResult(strategy=HookStrategy.CANCEL)
    
    @staticmethod
    def _eval(code: str, globs, **kwargs):
        locs = {}
        globs = globs.copy()
        global_args = "_globs"
        while global_args in globs.keys():
            global_args = "_" + global_args
        kwargs[global_args] = {}
        for glob in ["__name__", "__package__"]:
            kwargs[global_args][glob] = globs[glob]

        root = ast.parse(code, "exec")
        code = root.body

        ret_name = "_ret"
        ok = False
        while True:
            if ret_name in globs.keys():
                ret_name = "_" + ret_name
                continue
            for node in ast.walk(root):
                if isinstance(node, ast.Name) and node.id == ret_name:
                    ret_name = "_" + ret_name
                    break
                ok = True
            if ok:
                break

        if not code:
            return None

        if not any(isinstance(node, ast.Return) for node in code):
            for i in range(len(code)):
                if isinstance(code[i], ast.Expr):
                    if i == len(code) - 1 or not isinstance(code[i].value, ast.Call):
                        code[i] = ast.copy_location(ast.Expr(ast.Call(func=ast.Attribute(value=ast.Name(id=ret_name,
                                                                                                        ctx=ast.Load()),
                                                                                        attr="append", ctx=ast.Load()),
                                                                    args=[code[i].value], keywords=[])), code[-1])
        else:
            for node in code:
                if isinstance(node, ast.Return):
                    node.value = ast.List(elts=[node.value], ctx=ast.Load())

        code.append(ast.copy_location(ast.Return(value=ast.Name(id=ret_name, ctx=ast.Load())), code[-1]))

        # globals().update(**<global_args>)
        glob_copy = ast.Expr(ast.Call(func=ast.Attribute(value=ast.Call(func=ast.Name(id="globals", ctx=ast.Load()),
                                                                        args=[], keywords=[]),
                                                        attr="update", ctx=ast.Load()),
                                    args=[], keywords=[ast.keyword(arg=None,
                                                                    value=ast.Name(id=global_args, ctx=ast.Load()))]))
        ast.fix_missing_locations(glob_copy)
        code.insert(0, glob_copy)
        ret_decl = ast.Assign(targets=[ast.Name(id=ret_name, ctx=ast.Store())], value=ast.List(elts=[], ctx=ast.Load()))
        ast.fix_missing_locations(ret_decl)
        code.insert(1, ret_decl)
        args = []
        for a in list(map(lambda x: ast.arg(x, None), kwargs.keys())):
            ast.fix_missing_locations(a)
            args += [a]
        args = ast.arguments(args=[], vararg=None, kwonlyargs=args, kwarg=None, defaults=[],
                            kw_defaults=[None for i in range(len(args))])
        args.posonlyargs = []
        fun = ast.FunctionDef(name="tmp", args=args, body=code, decorator_list=[], returns=None)
        ast.fix_missing_locations(fun)
        mod = ast.parse("")
        mod.body = [fun]
        comp = compile(mod, "<string>", "exec")

        exec(comp, {}, locs)

        r = locs["tmp"](**kwargs)
        i = 0
        while i < len(r) - 1:
            if r[i] is None:
                del r[i]
            else:
                i += 1
        if len(r) == 1:
            [r] = r
        elif not r:
            r = None
        return r

    @command("eval", aliases=["e"], doc="eval_cmd")
    def eval_cmd(self, command: CactusUtils.Command):
        try:
            result = self._eval(command.raw_args, globals(), **{
                "self": self,
                "params": command.params,
                "cmd": command,
                "utils": self.utils,
            })
            result = self.utils.escape_html(str(result))
            if len(result) > 3072:
                file_path = self.utils.FileSystem.write_temp_file(f"eval-result.txt", result.encode("utf-8"))

                self.answer_file(command.params.peer, file_path, self.string("eval_result_file", self.utils.escape_html(command.raw_args)), replyToMsg=command.params.replyToMsg, replyToTopMsg=command.params.replyToTopMsg)
                self.utils.FileSystem.delete_file_after(file_path, 15)
                return HookResult(strategy=HookStrategy.CANCEL)
            
            result = self.string("eval_result", self.utils.escape_html(str(result)), self.utils.escape_html(command.raw_args))
        except Exception:
            result = self.string("eval_error", self.utils.escape_html(traceback.format_exc()), self.utils.escape_html(command.raw_args))

        self.answer(command.params, result)

        return HookResult(strategy=HookStrategy.CANCEL)

    @command(doc="set_prefix_doc")
    def setprefix(self, command: CactusUtils.Command):
        if not command.raw_args:
            self.utils.show_error(self.string("no_args"))
            return HookResult(strategy=HookStrategy.CANCEL)

        if len(command.raw_args) != 1:
            self.utils.show_error(self.string("prefix_must_be_one_char"))
            return HookResult(strategy=HookStrategy.CANCEL)

        self.set_setting("prefix", command.raw_args)
        self.utils.show_info(self.string("prefix_set", command.raw_args))
        return HookResult(strategy=HookStrategy.CANCEL)
    
    @command("plf", doc="plf_doc")
    def send_plugin_file(self, command: CactusUtils.Command):
        if not command.raw_args:
            self.utils.show_error(self.string("no_args"))
            return HookResult(strategy=HookStrategy.CANCEL)
        
        _plugins = sorted([
            p
            for p in plugins_manager.PluginsManager._plugins.values()
        ], key=lambda x: x.name.lower())

        query = command.raw_args.lower()

        for plugin in _plugins:
            if query in [plugin.name.lower(), plugin.id.lower()]:
                with open(PluginInfo(self, plugin).get_file_path(), "rb") as f:
                    path = self.utils.FileSystem.write_temp_file(f"{plugin.name}_{plugin.version or '-'}.plugin", f.read())

                self.answer_file(command.params.peer, path, self.string("plugin_file_sent", plugin=plugin, version=f"(v{plugin.version})" if plugin.version else ""), replyToMsg=command.params.replyToMsg, replyToTopMsg=command.params.replyToTopMsg)
                self.utils.FileSystem.delete_file_after(path, 30)
                return HookResult(strategy=HookStrategy.CANCEL)
            
        self.utils.show_error(self.string("plugin_not_found", query))
        return HookResult(strategy=HookStrategy.CANCEL)

    def _export_plugins_action(self, action: str, id: str = None, pl: str = ""):
        _plugins = sorted([
            p
            for p in plugins_manager.PluginsManager._plugins.values()
        ], key=lambda x: x.name.lower())

        try:
            if action == "export":
                if not pl:
                    return
                
                data = {}
                for plugin in _plugins:
                    if plugin.id not in pl and pl != "ALL":
                        continue
                    data[plugin.id] = PluginInfo(self, plugin, plugin in self.utils._plugins).export(with_data=True)
                path = self.utils.FileSystem.write_temp_file(f"plugins-export.cactusexport", self.utils.compress_and_encode(json.dumps(data).encode("utf-8")).encode("utf-8"))
                self.utils.FileSystem.delete_file_after(path, 40)
                return path

            plx = pl
            rnd = os.urandom(8).hex()
            if action == "add" and id:
                plx = ((plx + "+") if plx else "") + id
            elif action == "remove" and id:
                if plx == "ALL":
                    plx = "+".join([p.id for p in _plugins if p.id != id])
                else:
                    plx = plx.replace(f"{id}", "").replace("++", "+")
                
                if plx.endswith("+"):
                    plx = plx[:-1]
                if plx.startswith("+"):
                    plx = plx[1:]
            elif action == "clear":
                if not plx:
                    return
                
                plx = ""
            elif action == "addall":
                if plx == "ALL":
                    return
                
                plx = "ALL"
            elif action != "startup":
                return
            
            plugin_format = "[{emoji}] <a href='{action}'><b>{name}</b></a> {version}"

            text = self.string(
                "exporting_plugins",
                add_all=self.string("add_all", self.utils.Uri.create(self, "exportPlugins", action="addall", pl=plx, rnd=rnd)),
                clear=self.string("clear", self.utils.Uri.create(self, "exportPlugins", action="clear", pl=plx, rnd=rnd)),
                plugins="\n".join([
                    plugin_format.format(
                        emoji="❇️" if plugin.id in plx.split("+") or plx == "ALL" else "🔘",
                        action=self.utils.Uri.create(self, "exportPlugins", action="remove" if plugin.id in plx.split("+") or plx == "ALL" else "add", id=plugin.id, pl=plx, rnd=rnd),
                        name=plugin.name,
                        version=f"(v{plugin.version})" if plugin.version else "",
                    )
                    for plugin in _plugins
                ]),
                export=self.string("export", self.utils.Uri.create(self, "exportPlugins", action="export", pl=plx, rnd=rnd)),
            )
            return text
        except:
            self.error(traceback.format_exc())

    @command("cexport", doc="cexport_doc")
    def export_plugins(self, command: CactusUtils.Command):
        text = self._export_plugins_action("startup")

        return self.answer(command.params, text, parse_mode="HTML")

    @uri("exportPlugins")
    def export_plugins_uri(self, rnd: str, action: str, id: str = None, pl: str = ""):
        if not rnd:
            return
        
        def _fn(msg, fragment):
            if not msg:
                return
            
            self_id = get_user_config().getClientUserId()
            
            if msg.messageOwner.from_id.user_id == self_id:
                result = self._export_plugins_action(action, id, pl)
                if not result:
                    return
                
                if action != "export":
                    self.utils.edit_message(msg, result, parse_mode="HTML", fragment=fragment)
                else:
                    chat_id = None
                    peer = msg.messageOwner.peer_id
                    if isinstance(peer, TLRPC.TL_peerUser):
                        chat_id = peer.user_id
                    elif isinstance(peer, TLRPC.TL_peerChat):
                        chat_id = -peer.chat_id
                    elif isinstance(peer, TLRPC.TL_peerChannel):
                        chat_id = -peer.channel_id
                    else:
                        return
                    
                    self.answer_file(chat_id, result, "EXPORT", parse_mode="HTML", editingMessageObject=msg) # EXPORT
        
        self.utils.get_message_by_rnd_in_current_chat(rnd, _fn)

    def _open_export_plugins_alert(self, ctx):
        CactusIEAlert(self, ctx.get("context"), isExport=True, ctx=ctx).show_alert()

class CactusIEAlert:
    def __init__(self, lib, activity, isExport: bool = False, plugins: Optional[Dict] = None, ctx=None):
        self.current_plugins = {
            p.id: p
            for p in sorted([
                p
                for p in plugins_manager.PluginsManager._plugins.values()
            ], key=lambda x: x.name.lower())
        }
        self.isExport = isExport
        self.with_data = True

        self.selected_plugins = {
            plugin_id: True
            for plugin_id in (plugins if not isExport else self.current_plugins)
        }
        self._new_selected_plugins = {}
        self.ctx = ctx

        self.plugins = plugins
        self.lib = lib
        self.activity = activity

    def string(self, key, *args, **kwargs):
        return self.lib.string(("import_" if not self.isExport else "export_") + key, *args, **kwargs)

    def _current_version(self, plugin_id):
        v = getattr(self.current_plugins.get(plugin_id, None), "version", None)
        return f"v{v} -> " if v else "", v
    
    def _select_plugins_dialog(self, v=None):
        try:
            self._new_selected_plugins.clear()
            self._new_selected_plugins.update(self.selected_plugins)
            cells = {}
            _builder = AlertDialogBuilder(self.activity)
            _builder.set_title(
                self.lib.string("select_plugins") if self.isExport else self.string("alert_title", "")
            )

            container = LinearLayout(self.activity)
            container.setOrientation(LinearLayout.VERTICAL)
            container.setPadding(0, AndroidUtilities.dp(8), 0, AndroidUtilities.dp(8))

            def _on_click(id):
                def _(v=None):
                    self._new_selected_plugins[id] = not self._new_selected_plugins.get(id)
                    cells[id].setChecked(self._new_selected_plugins[id], True)
                    self._update_texts(True)
                return _
            
            if self.isExport:
                for plugin_id, plugin in self.current_plugins.items():
                    version = getattr(self.current_plugins.get(plugin_id, None), "version", None)
                    
                    cell = CheckBoxCell(self.activity, 1, get_last_fragment().getResourceProvider())
                    cell.setBackgroundDrawable(Theme.getSelectorDrawable(False))
                    cell.setText(plugin.name, ("v" + version) if version else "", self._new_selected_plugins[plugin_id], False, False)
                    
                    cell.setPadding(0, 0, 0, 0)
                    cell.setEnabled(True)
                    cells[plugin_id] = cell
                    container.addView(cell, LayoutHelper.createLinear(LinearLayout.LayoutParams.MATCH_PARENT, -2))

                    cell.setOnClickListener(OnClickListener(_on_click(plugin_id)))
            else:
                for plugin_id, plugin_info in self.plugins.items():
                    version = plugin_info["plugin_meta"].get("version", None) or "?"
                    merge, current_version = self._current_version(plugin_id)
                    version = "" if not current_version and not version else (f"{merge}v{version}" if version != current_version else f"v{version}")

                    cell = CheckBoxCell(self.activity, 1, get_last_fragment().getResourceProvider())
                    cell.setBackgroundDrawable(Theme.getSelectorDrawable(False))
                    cell.setText(plugin_info["plugin_meta"]["name"], version.replace("v?", ""), self._new_selected_plugins[plugin_id], False, False)

                    cell.getValueTextView().setTextColor(
                        Theme.getColor(
                            Theme.key_text_RedRegular
                            if version == (current_version or "?")
                            else Theme.key_dialogTextBlue
                            if version != current_version and current_version
                            else Theme.key_color_green
                        )
                    )
                    
                    cell.setPadding(0, 0, 0, 0)
                    cell.setEnabled(True)
                    cells[plugin_id] = cell
                    container.addView(cell, LayoutHelper.createLinear(LinearLayout.LayoutParams.MATCH_PARENT, -2))

                    cell.setOnClickListener(OnClickListener(_on_click(plugin_id)))

            _builder.set_view(container)

            def _ok(b, w):
                try:
                    self.selected_plugins.clear()
                    self.selected_plugins.update(self._new_selected_plugins)
                    self._new_selected_plugins.clear()
                    self._update_texts()
                except:
                    self.lib.error(traceback.format_exc())

            def _cancel(b, w):
                b.dismiss()
                self._update_texts()

            _builder.set_positive_button("OK", _ok)
            _builder.set_negative_button(self.lib.string("cancel"), _cancel)
            _builder.show()
        except:
            self.lib.error(traceback.format_exc())
    
    def _update_texts(self, mode: bool = False):
        k = len([i for i, t in (self.selected_plugins if not mode else self._new_selected_plugins).items() if t])
        (self.titleTextView if not self.isExport else self.selectPluginsBtn).setText(
            (
                self.string("alert_title", self.plur(k))
                if not self.isExport
                else self.lib.string("selected_plugins", self.plur(k))
            ) + (" *" if mode else "")
        )

        self.doneBtn.setClickable(k > 0)
    
    def getIconView(self):
        self.iconView = imageView = BackupImageView(self.activity)
        imageView.setRoundRadius(AndroidUtilities.dp(12))
        imageView.getImageReceiver().setAutoRepeat(1)
        imageView.getImageReceiver().setAutoRepeatCount(1)

        return imageView
    
    def setSticker(self, path: str, imageView: Optional[Any] = None):
        get_media_data_controller().setPlaceholderImageByIndex(imageView if imageView else self.iconView, path.split("/")[0], int(path.split("/")[1]), "200_200")

    def show_alert(self):
        try:
            builder = BottomSheet.Builder(self.activity)
            self._builder = builder
            self.dismiss = builder.getDismissRunnable()

            builder.setApplyTopPadding(False)
            builder.setApplyBottomPadding(False)
            linearLayout = LinearLayout(self.activity)
            builder.setCustomView(linearLayout)
            linearLayout.setOrientation(LinearLayout.VERTICAL)

            linearLayout.addView(self.getIconView(), LayoutHelper.createLinear(78, 78, Gravity.CENTER_HORIZONTAL, 0, 28, 0, 0))
            self.setSticker("CactusPlugins/" + ("3" if self.isExport else "1"))
            
            self.titleTextView = titleTextView = TextView(self.activity)
            titleTextView.setTextColor(Theme.getColor(Theme.key_dialogTextBlack))
            titleTextView.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 22)
            titleTextView.setGravity(Gravity.CENTER)
            if self.isExport:
                titleTextView.setText(self.string("title"))
            linearLayout.addView(titleTextView, LayoutHelper.createFrame(-1, -2, Gravity.TOP, 0, 8, 0, 16))

            # lineView = View(self.activity)
            # lineView.setBackgroundColor(Theme.getColor(Theme.key_divider))
            # linearLayout.addView(lineView, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 1))

            self.preProcess = preProcess = LinearLayout(self.activity)
            preProcess.setOrientation(LinearLayout.VERTICAL)

            self.infoTextView = infoTextView = TextView(self.activity)
            infoTextView.setTextColor(Theme.getColor(Theme.key_dialogTextGray4))
            infoTextView.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 14)
            infoTextView.setGravity(Gravity.CENTER)
            infoTextView.setText(self.string("info"))
            preProcess.addView(infoTextView, LayoutHelper.createLinear(-1, -2, (Gravity.RIGHT if LocaleController.isRTL else Gravity.LEFT) | Gravity.TOP, 17, 8, 17, 8))

            self.warningTextView = warningTextView = TextView(self.activity)
            warningTextView.setTextColor(Theme.getColor(Theme.key_text_RedRegular))
            warningTextView.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 14)
            warningTextView.setGravity(Gravity.CENTER)
            warningTextView.setText(self.string("warning"))
            preProcess.addView(warningTextView, LayoutHelper.createLinear(-1, -2, (Gravity.RIGHT if LocaleController.isRTL else Gravity.LEFT) | Gravity.TOP, 50, 0, 50, 16))

            self.selectPluginsBtn = selectPluginsBtn = TextView(self.activity)
            selectPluginsBtn.setText(self.lib.string("select_plugins"))
            selectPluginsBtn.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 16)
            selectPluginsBtn.setGravity(Gravity.CENTER)
            selectPluginsBtn.setClickable(True)
            selectPluginsBtn.setTextColor(Theme.getColor(Theme.key_featuredStickers_addButton))
            selectPluginsBtn.setOnClickListener(OnClickListener(self._select_plugins_dialog))
            preProcess.addView(selectPluginsBtn, LayoutHelper.createFrame(-1, 32, (Gravity.RIGHT if LocaleController.isRTL else Gravity.LEFT) | Gravity.TOP, 100, 8, 100, 8))

            self.doneBtn = doneBtn = TextView(self.activity)
            doneBtn.setText(self.lib.string("export2" if self.isExport else "import"))
            doneBtn.setTextColor(Theme.getColor(Theme.key_dialogTextBlack))
            doneBtn.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 16)
            doneBtn.setGravity(Gravity.CENTER)
            doneBtn.setBackground(Theme.createSimpleSelectorRoundRectDrawable(
                AndroidUtilities.dp(6),
                Theme.getColor(Theme.key_featuredStickers_addButton),
                Theme.getColor(Theme.key_featuredStickers_addButtonPressed)
            ))
            doneBtn.setClickable(True)
            doneBtn.setTextColor(Theme.getColor(Theme.key_featuredStickers_buttonText))
            doneBtn.setOnClickListener(OnClickListener(self.start_process))
            preProcess.addView(doneBtn, LayoutHelper.createFrame(-1, 56, (Gravity.RIGHT if LocaleController.isRTL else Gravity.LEFT) | Gravity.TOP, 30, 8, 30, 8))


            includeDataCheckbox = CheckBox2(self.activity, 21, get_last_fragment().getResourceProvider())
            includeDataCheckbox.setColor(Theme.key_radioBackgroundChecked, Theme.key_checkboxDisabled, Theme.key_checkboxCheck)
            includeDataCheckbox.setDrawUnchecked(True)
            includeDataCheckbox.setChecked(self.with_data, False)
            includeDataCheckbox.setDrawBackgroundAsArc(10)

            includeDataTextView = TextView(self.activity)
            includeDataTextView.setTextColor(Theme.getColor(Theme.key_windowBackgroundWhiteBlackText))
            includeDataTextView.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 14)
            includeDataTextView.setText(self.lib.string("include_data_and_settings"))
            includeDataCheckBoxContainer = FrameLayout(self.activity)
            includeDataCheckBoxContainer.addView(includeDataCheckbox, LayoutHelper.createFrame(21, 21, Gravity.CENTER, 0, 0, 0, 0));

            includeDataCheckLayout = LinearLayout(self.activity)
            includeDataCheckLayout.setOrientation(LinearLayout.HORIZONTAL)
            includeDataCheckLayout.setPadding(AndroidUtilities.dp(8), AndroidUtilities.dp(6), AndroidUtilities.dp(10), AndroidUtilities.dp(6))
            includeDataCheckLayout.addView(includeDataCheckBoxContainer, LayoutHelper.createLinear(24, 24, Gravity.CENTER_VERTICAL, 0, 0, 6, 0))
            includeDataCheckLayout.addView(includeDataTextView, LayoutHelper.createLinear(-2, -2, Gravity.CENTER_VERTICAL))

            def _on_include_data_cell_click(*args):
                self.with_data = not includeDataCheckbox.isChecked()
                includeDataCheckbox.setChecked(self.with_data, True)

            includeDataCheckLayout.setOnClickListener(OnClickListener(_on_include_data_cell_click))

            includeDataCheckLayout.setBackground(Theme.createRadSelectorDrawable(Theme.getColor(Theme.key_listSelector), 8, 8))
            preProcess.addView(includeDataCheckLayout, LayoutHelper.createLinear(-2, -2, Gravity.CENTER_HORIZONTAL, 0, 0, 0, 8))
            
            linearLayout.addView(preProcess, LayoutHelper.createLinear(-1, -2, Gravity.TOP, 0, 0, 0, 0))

            self.onProcess = onProcess = LinearLayout(self.activity)
            onProcess.setOrientation(LinearLayout.VERTICAL)
            onProcess.setPadding(0, 0, 0, AndroidUtilities.dp(16))

            onProcess.setVisibility(View.GONE)
            
            self.loadingProgress = loadingProgress = LineProgressView(self.activity)
            loadingProgress.setProgressColor(Theme.getColor(Theme.key_dialogLineProgress))
            loadingProgress.setProgress(0, True)
            onProcess.addView(loadingProgress, LayoutHelper.createFrame(-1, 4, Gravity.TOP, 26, 8, 26, 0))

            self.progressPercentage = progressPercentage = TextView(self.activity)
            progressPercentage.setTextColor(Theme.getColor(Theme.key_dialogTextBlack))
            progressPercentage.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 16)
            progressPercentage.setText("0%")
            progressPercentage.setGravity(Gravity.LEFT)
            onProcess.addView(progressPercentage, LayoutHelper.createFrame(-1, -2, Gravity.TOP, 26, 0, 0, 8))

            self.progressTextView = progressTextView = TextView(self.activity)
            progressTextView.setTextColor(Theme.getColor(Theme.key_dialogTextBlack))
            progressTextView.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 16)
            progressTextView.setText(self.lib.string("processing"))
            progressTextView.setGravity(Gravity.LEFT)
            onProcess.addView(progressTextView, LayoutHelper.createFrame(-1, -2, Gravity.TOP, 26, 0, 0, 0))
            
            linearLayout.addView(onProcess, LayoutHelper.createLinear(-1, -2, Gravity.TOP, 0, 0, 0, 0))

            self._update_texts()
            self.bottomSheet = builder.show()
        except:
            self.lib.error(traceback.format_exc())
    
    def process(self):
        try:
            plids = [i for i, t in self.selected_plugins.items() if t]
            if self.isExport:
                data = {}
                for index, plugin_id in enumerate(plids, 1):
                    data[plugin_id] = CactusUtils.PluginInfo(
                        self.lib,
                        self.current_plugins[plugin_id],
                        getattr(getattr(getattr(self.current_plugins[plugin_id], "utils", None), "__class__", None), "__name__", None) == "CactusUtils"
                    ).export(with_data=self.with_data)
                    if index != len(plids):
                        self._update_progress(index, len(plids))

                path = CactusUtils.FileSystem.write_temp_file(f"plugins-export.cactusexport", CactusUtils.compress_and_encode(json.dumps(data).encode("utf-8")).encode("utf-8"))
                self.lib.answer_file(self.ctx.get("dialog_id"), path, "export! :D")
                CactusUtils.FileSystem.delete_file_after(path, 30)

                self._update_progress(len(plids), len(plids))
            else:
                self.loaded_plugins = 0
                self.plugins_count = len(plids)
                for index, plugin_id in enumerate(plids, 1):
                    if plugin_id in self.current_plugins:
                        PluginsController.getInstance().deletePlugin(
                            plugin_id,
                            CactusUtils.Callback(self._load_plugin, self.plugins[plugin_id])
                        )
                    else:
                        self._load_plugin(None, self.plugins[plugin_id])

        except:
            self.lib.error(traceback.format_exc())
    
    def _load_data(self, plugin_data: dict, pc):
        if not self.with_data:
            self.loaded_plugins += 1
            self._update_progress(self.loaded_plugins, self.plugins_count)
            return
        
        plugin_id = plugin_data["plugin_meta"]["id"]
        
        if plugin_data.get("settings", {}):
            for key, value in plugin_data["settings"].items():
                getattr(
                    pc,
                    "setPluginSetting" + (
                        "Boolean" if isinstance(value, bool) else
                        "Int" if isinstance(value, int) else
                        "String"
                    ),
                    lambda _, __, ___: None
                )(plugin_id, key, value if isinstance(value, (str, bool, int)) or value is None else str(value))
        
        if plugin_data.get("data", {}):
            getattr(plugins_manager._plugins.get(plugin_id), "import_data", lambda _: None)(plugin_data["data"])
        
        self.loaded_plugins += 1
        self._update_progress(self.loaded_plugins, self.plugins_count)
    
    def _load_plugin(self, error, plugin_data: dict):
        meta = plugin_data.get("plugin_meta", {})
        pid = meta.get("id")

        if error:
            self.lib.error(f"Failed to unload plugin {pid}: {error}")
            return
        
        pc = PluginsController.getInstance()

        def _enabled_cb(error):
            if error:
                self.lib.error(f"Failed to enable plugin {pid}: {error}")
                return

        def _load_cb(error):
            if error:
                self.lib.error(f"Failed to load plugin {pid}: {error}")
                # return

            if meta.get("enabled", False):
                pc.setPluginEnabled(pid, True, CactusUtils.Callback(_enabled_cb))
            
            self._load_data(plugin_data, pc)

        path = CactusUtils.FileSystem.write_temp_file(f"{pid}.plugin", CactusUtils.decode_and_decompress(plugin_data["file_content"]))
        self.lib.debug(f"Loading plugin {pid} from file: {path}")
        pc.loadPluginFromFile(str(path), CactusUtils.Callback(_load_cb))
        CactusUtils.FileSystem.delete_file_after(path, 30)
        
    def plur(self, k):
        return CactusUtils.pluralization_string(k, ["плагин", "плагина", "плагинов"]) if CactusUtils.get_locale() == "ru" else (f"{k} plugin" + ("s" if k > 1 else ""))

    def _update_progress(self, index: int, count: int):
        try:
            if get_private_field(self.bottomSheet, "showing") is False:
                self.bottomSheet.show()
            
            self.loadingProgress.setProgress(
                jfloat((round((index / count) * 100) / 100) if index < count else 1),
                True
            )
            self.progressTextView.setText(self.string("progress", self.plur(index)) + "...")
            self.progressPercentage.setText(
                (str(round((index / count) * 100)) + "%")
                if index < count else "100%"
            )
            if index == count:
                self.setSticker("CactusPlugins/2")
                with suppress(Exception):
                    self.onProcess.setVisibility(View.GONE)
                
                self.titleTextView.setText(self.string("done", self.plur(index)))
                time.sleep(0.65)
                run_on_ui_thread(lambda: self.dismiss.run())
        except:
            self.lib.error(traceback.format_exc())

    def start_process(self):
        try:
            self.preProcess.setVisibility(View.GONE)
            self.onProcess.setVisibility(View.VISIBLE)
            self.bottomSheet.setCanDismissWithSwipe(False)
            
            run_on_queue(self.process)
        except:
            self.lib.error(traceback.format_exc())



class UriHandler(MethodHook):
    def __init__(self, plugin: CactusLib):
        self.plugin = plugin

    def after_hooked_method(self, param):
        uri = str(param.args[1].toString())
        m = re.match("tg://cactus/(.+)/(.+)", uri)
        if not m:
            return
        
        self.plugin.debug(f"Clicked {uri}")
        
        plugin_id = m.group(1)
        parsed = urlparse(m.group(2))
        command = parsed.path
        kwargs = {} if not parsed.query else {
            k: v[0]
            for k, v in parse_qs(parsed.query).items()
        }
        
        self.plugin.execute_on_uri_command(plugin_id, command, kwargs)


class DocumentHandler(MethodHook):
    def __init__(self, plugin):
        self.lib = plugin
    
    def before_hooked_method(self, param):
        try:
            f = param.args[0]
            filename = param.args[1]
            if filename.split(".")[-1] == "cactusexport":
                with open(f.getAbsolutePath(), "rb") as f:
                    content = f.read()
                
                if not content:
                    return
                
                param.setResult(False)

                content = json.loads(CactusUtils.decode_and_decompress(content))
                CactusIEAlert(self.lib, param.args[3], plugins=content).show_alert()
            return
        except:
            self.lib.error(traceback.format_exc())

