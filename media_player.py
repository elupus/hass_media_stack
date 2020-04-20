"""Media Stack."""
import logging

import voluptuous as vol

from homeassistant.components.media_player import (
    PLATFORM_SCHEMA,
    MediaPlayerDevice,
    ATTR_TO_PROPERTY,
)
from homeassistant.components.media_player.const import (
    ATTR_APP_ID,
    ATTR_APP_NAME,
    ATTR_INPUT_SOURCE,
    ATTR_INPUT_SOURCE_LIST,
    ATTR_MEDIA_ALBUM_ARTIST,
    ATTR_MEDIA_ALBUM_NAME,
    ATTR_MEDIA_ARTIST,
    ATTR_MEDIA_CHANNEL,
    ATTR_MEDIA_CONTENT_ID,
    ATTR_MEDIA_CONTENT_TYPE,
    ATTR_MEDIA_DURATION,
    ATTR_MEDIA_EPISODE,
    ATTR_MEDIA_PLAYLIST,
    ATTR_MEDIA_POSITION,
    ATTR_MEDIA_POSITION_UPDATED_AT,
    ATTR_MEDIA_SEASON,
    ATTR_MEDIA_SEEK_POSITION,
    ATTR_MEDIA_SERIES_TITLE,
    ATTR_MEDIA_SHUFFLE,
    ATTR_MEDIA_TITLE,
    ATTR_MEDIA_TRACK,
    ATTR_MEDIA_VOLUME_LEVEL,
    ATTR_MEDIA_VOLUME_MUTED,
    ATTR_SOUND_MODE_LIST,
    DOMAIN,
    SERVICE_CLEAR_PLAYLIST,
    SERVICE_PLAY_MEDIA,
    SERVICE_SELECT_SOURCE,
    SUPPORT_CLEAR_PLAYLIST,
    SUPPORT_SELECT_SOURCE,
    SUPPORT_SHUFFLE_SET,
    SUPPORT_TURN_OFF,
    SUPPORT_TURN_ON,
    SUPPORT_VOLUME_MUTE,
    SUPPORT_VOLUME_SET,
    SUPPORT_VOLUME_STEP,
)
from homeassistant.const import (
    ATTR_ENTITY_PICTURE,
    ATTR_SUPPORTED_FEATURES,
    ATTR_ASSUMED_STATE,
    ATTR_ICON,
    CONF_NAME,
    STATE_IDLE,
    STATE_OFF,
    STATE_UNAVAILABLE,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

_LOGGER = logging.getLogger(__name__)

ATTR_ACTIVE_CHILD = "active_child"
ATTR_DATA = "data"

CONF_ATTRS = "attributes"
CONF_CHILDREN = "children"
CONF_COMMANDS = "commands"
CONF_SERVICE = "service"
CONF_SERVICE_DATA = "service_data"
CONF_AUDIO = "audio"
CONF_VIDEO = "video"
CONF_MAPPING = "mapping"

OFF_STATES = [STATE_IDLE, STATE_OFF, STATE_UNAVAILABLE]

ATTRS_SCHEMA = cv.schema_with_slug_keys(cv.string)
CMD_SCHEMA = cv.schema_with_slug_keys(cv.SERVICE_SCHEMA)


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Optional(CONF_AUDIO, default=[]): cv.entity_ids,
        vol.Optional(CONF_VIDEO, default=[]): cv.entity_ids,
        vol.Required(CONF_MAPPING): {cv.entity_id: {str: cv.entity_id}},
    },
)

STATE_ATTR_TO_COPY = [*ATTR_TO_PROPERTY, "entity_picture_local"]


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the universal media players."""
    player = MediaStack(config)

    async_add_entities([player])


class MediaStack(MediaPlayerDevice):
    """Representation of an universal media player."""

    def __init__(self, config):
        """Initialize player."""
        self._audio = config[CONF_AUDIO]
        self._video = config[CONF_VIDEO]
        self._mapping = config[CONF_MAPPING]
        self._name = config[CONF_NAME]
        self._stack = []

    async def async_added_to_hass(self):
        """Subscribe to children."""

        @callback
        def async_on_dependency_update(*_):
            """Update ha state when dependencies update."""
            self.async_schedule_update_ha_state(True)

        depend = set()
        depend |= set(self._audio)
        depend |= set(self._video)

        self.hass.helpers.event.async_track_state_change(
            list(depend), async_on_dependency_update
        )

    @property
    def name(self):
        """Return the name of universal player."""
        return self._name

    def _get_source_stack(self, entity_id):

        stack = []
        entity_ids = set()
        while True:
            data = self.hass.states.get(entity_id)
            if data is None or data.state in OFF_STATES:
                return stack

            if entity_id in entity_ids:
                _LOGGER.warning("Recursive media stack")
                return stack
            entity_ids.add(entity_id)
            stack.append(data)

            try:
                mapping = self._mapping[entity_id]
                source = data.attributes[ATTR_INPUT_SOURCE]
                entity_id = mapping[source]
            except KeyError:
                return stack

    def _get_attribute(self, attribute, default=None):
        if self._stack:
            return self._stack[-1].attributes.get(attribute)
        else:
            return default

    @property
    def state(self):
        """Return the current state of the media player."""
        if self._stack:
            return self._stack[-1].state
        else:
            return STATE_OFF

    @property
    def source(self):
        """Return the current state of the media player."""
        if self._stack:
            data = [x.attributes.get(ATTR_INPUT_SOURCE) for x in self._stack]
            return " - ".join(filter(None, data))
        else:
            return None

    @property
    def entity_picture_local(self):
        """Return if picture is available locally."""
        return self._get_attribute("entity_picture_local")

    @property
    def state_attributes(self):
        """Return the state attributes."""
        if self.state == STATE_OFF:
            return None

        attrs = {}

        for attr in ATTR_TO_PROPERTY:
            value = getattr(self, attr)
            if value is None:
                value = self._get_attribute(attr)

            if value is not None:
                attrs[attr] = value

        return attrs

    @property
    def supported_features(self):
        """Return the current state of the media player."""
        return self._get_attribute(ATTR_SUPPORTED_FEATURES, 0) | SUPPORT_SELECT_SOURCE

    @property
    def assumed_state(self):
        """Return the current state of the media player."""
        return self._get_attribute(ATTR_ASSUMED_STATE)

    @property
    def entity_picture(self):
        """Return the current state of the media player."""
        return self._get_attribute(ATTR_ENTITY_PICTURE)

    @property
    def icon(self):
        """Return the current state of the media player."""
        return self._get_attribute(ATTR_ICON)

    @property
    def sound_mode_list(self):
        """Return the current state of the media player."""
        return self._get_attribute(ATTR_SOUND_MODE_LIST)

    @property
    def source_list(self):
        """Return the current state of the media player."""

        def _get_sources(entity_id):
            data = self.hass.states.get(entity_id)
            if data is None:
                return []
            source = data.attributes.get(ATTR_INPUT_SOURCE)
            sources = list(data.attributes.get(ATTR_INPUT_SOURCE_LIST, []))
            if source and source not in sources:
                sources.append(source)
            return sources

        def _get_source_tree(entity_id):
            result = {}
            mapping = self._mapping.get(entity_id, {})
            for source in _get_sources(entity_id):
                source_entity_id = mapping.get(source)
                if source_entity_id:
                    result[source] = _get_source_tree(source_entity_id)
                else:
                    result[source] = {}
            return result

        def _flatten(tree):
            for key, value in tree.items():
                added = False
                for x in _flatten(value):
                    yield f"{key} - {x}"
                    added = True

                if not added:
                    yield f"{key}"

        tree = _get_source_tree(self._video[0])
        return list(_flatten(tree))

        return self._get_attribute(ATTR_INPUT_SOURCE_LIST)

    async def async_update(self):
        """Update state in HA."""
        self._stack = self._get_source_stack(self._video[0])
