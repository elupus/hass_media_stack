"""Media Stack."""
import logging

import voluptuous as vol

from homeassistant.components.media_player import (
    PLATFORM_SCHEMA,
    MediaPlayerDevice,
    ATTR_TO_PROPERTY,
    ATTR_MEDIA_VOLUME_LEVEL,
    ATTR_MEDIA_VOLUME_MUTED,
)
from homeassistant.components.media_player.const import (
    ATTR_INPUT_SOURCE,
    ATTR_INPUT_SOURCE_LIST,
    ATTR_SOUND_MODE_LIST,
    SUPPORT_SELECT_SOURCE,
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
from homeassistant.core import callback, State
from homeassistant.helpers import config_validation as cv

_LOGGER = logging.getLogger(__name__)

CONF_MAPPING = "mapping"
CONF_VOLUME = "volume"

OFF_STATES = [STATE_IDLE, STATE_OFF, STATE_UNAVAILABLE]


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_MAPPING): {cv.entity_id: {str: cv.entity_id}},
        vol.Optional(CONF_VOLUME, []): cv.entity_ids,
    },
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the universal media players."""
    player = MediaStack(config)

    async_add_entities([player])


class MediaStack(MediaPlayerDevice):
    """Representation of an universal media player."""

    def __init__(self, config):
        """Initialize player."""
        self._mapping = config[CONF_MAPPING]
        self._name = config[CONF_NAME]
        self._volume = config[CONF_VOLUME]
        self._stack = []

    async def async_added_to_hass(self):
        """Subscribe to children."""

        @callback
        def async_on_dependency_update(*_):
            """Update ha state when dependencies update."""
            self.async_schedule_update_ha_state(True)

        self.hass.helpers.event.async_track_state_change(
            list(self._mapping.keys()), async_on_dependency_update
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

    @property
    def _volume_entity(self):
        if not self._stack:
            return None

        for entity_id in self._volume:
            value = next((x for x in self._stack if x.entity_id == entity_id), None)
            if value:
                return value
        return None

    @property
    def _source_entity(self):
        if not self._stack:
            return None
        return self._stack[-1]

    @property
    def _root_entity_id(self):
        return next(iter(self._mapping))

    def _get_attribute(self, state: State, attribute: str, default=None):
        if state:
            return state.attributes.get(attribute)
        else:
            return default

    @property
    def state(self):
        """Return the current state of the media player."""
        data = self._source_entity
        if data:
            return data.state
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
    def volume_level(self):
        """Volume level of the media player (0..1)."""
        return self._get_attribute(self._volume_entity, ATTR_MEDIA_VOLUME_LEVEL)

    @property
    def is_volume_muted(self):
        """Boolean if volume is currently muted."""
        return self._get_attribute(self._volume_entity, ATTR_MEDIA_VOLUME_MUTED)


    @property
    def entity_picture_local(self):
        """Return if picture is available locally."""
        return self._get_attribute(self._source_entity, "entity_picture_local")

    @property
    def state_attributes(self):
        """Return the state attributes."""
        if self.state == STATE_OFF:
            return None

        attrs = {}

        for attr in ATTR_TO_PROPERTY:
            value = getattr(self, attr)
            if value is None:
                value = self._get_attribute(self._source_entity, attr)

            if value is not None:
                attrs[attr] = value

        return attrs

    @property
    def supported_features(self):
        """Return the current state of the media player."""
        supported = self._get_attribute(self._source_entity, ATTR_SUPPORTED_FEATURES, 0)

        supported |= SUPPORT_SELECT_SOURCE

        supported_volume = SUPPORT_VOLUME_MUTE | SUPPORT_VOLUME_SET | SUPPORT_VOLUME_STEP
        supported &= ~supported_volume
        supported |= self._get_attribute(self._volume_entity, ATTR_SUPPORTED_FEATURES, 0)

        return supported

    @property
    def assumed_state(self):
        """Return the current state of the media player."""
        return self._get_attribute(self._source_entity, ATTR_ASSUMED_STATE)

    @property
    def entity_picture(self):
        """Return the current state of the media player."""
        return self._get_attribute(self._source_entity, ATTR_ENTITY_PICTURE)

    @property
    def icon(self):
        """Return the current state of the media player."""
        return self._get_attribute(self._source_entity, ATTR_ICON)

    @property
    def sound_mode_list(self):
        """Return the current state of the media player."""
        return self._get_attribute(self._source_entity, ATTR_SOUND_MODE_LIST)

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

        tree = _get_source_tree(self._root_entity_id)
        return list(_flatten(tree))

    async def async_update(self):
        """Update state in HA."""
        self._stack = self._get_source_stack(self._root_entity_id)
