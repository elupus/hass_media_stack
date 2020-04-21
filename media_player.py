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

OFF_STATES = [STATE_IDLE, STATE_OFF, STATE_UNAVAILABLE]


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_MAPPING): {cv.entity_id: {str: cv.entity_id}},
    },
)


def _get_sources(attributes):
    source = attributes.get(ATTR_INPUT_SOURCE)
    sources = list(attributes.get(ATTR_INPUT_SOURCE_LIST, []))
    if source and source not in sources:
        sources.append(source)
    return sources


def _flatten_source(tree):
    source = tree["source"]
    if not source:
        return tree['name']

    child = tree["source_list"].get(source)
    if child:
        return _flatten_source(child)
    else:
        return f"{tree['name']}: {source}"


def _flatten_source_list(tree):
    if not tree["source_list"]:
        yield tree['name']

    for source, value in tree["source_list"].items():
        if value:
            yield from _flatten_source_list(value)
        else:
            yield f"{tree['name']}: {source}"


def _get_source_tree(hass, mappings, entity_id: str, parents: set):
    state = hass.states.get(entity_id)
    if state is None:
        return {}

    parents = set(parents)
    parents.add(entity_id)

    result = {}
    mapping = mappings.get(entity_id, {})
    for source in _get_sources(state.attributes):
        result[source] = {}

        source_entity_id = mapping.get(source)
        if not source_entity_id:
            continue

        if source_entity_id in parents:
            _LOGGER.debug(
                "Ignoring recursive loop: %s %s %s", entity_id, source, source_entity_id
            )
            continue

        result[source] = _get_source_tree(hass, mappings, source_entity_id, parents)

    return {
        "entity_id": state.entity_id,
        "name": state.name,
        "source": state.attributes.get(ATTR_INPUT_SOURCE),
        "source_list": result,
    }


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
        self._tree = {}

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

    @property
    def _source_entity(self):

        def _flatten(tree):
            source = tree["source"]
            child = tree["source_list"].get(source)
            if child:
                return _flatten(child)
            else:
                return self.hass.states.get(tree["entity_id"])

        if not self._tree:
            return None
        else:
            return _flatten(self._tree)

    @property
    def _sink_entity(self):
        for entity_id in self._mapping:
            state = self.hass.states.get(entity_id)
            if state and state.state not in OFF_STATES:
                return state
        return None

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
        if self._tree:
            return _flatten_source(self._tree)
        else:
            return None

    @property
    def volume_level(self):
        """Volume level of the media player (0..1)."""
        return self._get_attribute(self._sink_entity, ATTR_MEDIA_VOLUME_LEVEL)

    @property
    def is_volume_muted(self):
        """Boolean if volume is currently muted."""
        return self._get_attribute(self._sink_entity, ATTR_MEDIA_VOLUME_MUTED)

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

        supported_volume = (
            SUPPORT_VOLUME_MUTE | SUPPORT_VOLUME_SET | SUPPORT_VOLUME_STEP
        )
        supported &= ~supported_volume
        supported |= self._get_attribute(self._sink_entity, ATTR_SUPPORTED_FEATURES, 0)

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

        if self._tree:
            return list(_flatten_source_list(self._tree))
        else:
            return None

    async def async_update(self):
        """Update state in HA."""
        state = self._sink_entity
        if state:
            self._tree = _get_source_tree(
                self.hass, self._mapping, state.entity_id, set()
            )
        else:
            self._tree = {}
