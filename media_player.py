"""Media Stack."""
import logging
from typing import Dict, Optional, Any
import voluptuous as vol
from dataclasses import dataclass

from homeassistant.components.media_player import (
    ATTR_MEDIA_SEEK_POSITION,
    ATTR_MEDIA_VOLUME_LEVEL,
    ATTR_MEDIA_VOLUME_MUTED,
    ATTR_TO_PROPERTY,
    DOMAIN,
    PLATFORM_SCHEMA,
    MediaPlayerDevice,
)
from homeassistant.components.media_player.const import (
    ATTR_INPUT_SOURCE,
    ATTR_INPUT_SOURCE_LIST,
    ATTR_MEDIA_CONTENT_ID,
    ATTR_MEDIA_CONTENT_TYPE,
    ATTR_SOUND_MODE_LIST,
    ATTR_MEDIA_SHUFFLE,
    SERVICE_CLEAR_PLAYLIST,
    SERVICE_PLAY_MEDIA,
    SUPPORT_SELECT_SOURCE,
    SUPPORT_VOLUME_MUTE,
    SUPPORT_VOLUME_SET,
    SUPPORT_VOLUME_STEP,
)
from homeassistant.const import (
    ATTR_ASSUMED_STATE,
    ATTR_ENTITY_ID,
    ATTR_ENTITY_PICTURE,
    ATTR_ICON,
    ATTR_SUPPORTED_FEATURES,
    CONF_NAME,
    SERVICE_MEDIA_NEXT_TRACK,
    SERVICE_MEDIA_PAUSE,
    SERVICE_MEDIA_PLAY,
    SERVICE_MEDIA_PLAY_PAUSE,
    SERVICE_MEDIA_PREVIOUS_TRACK,
    SERVICE_MEDIA_SEEK,
    SERVICE_MEDIA_STOP,
    SERVICE_SHUFFLE_SET,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    SERVICE_VOLUME_DOWN,
    SERVICE_VOLUME_MUTE,
    SERVICE_VOLUME_SET,
    SERVICE_VOLUME_UP,
    STATE_IDLE,
    STATE_OFF,
    STATE_UNAVAILABLE,
)
from homeassistant.core import State, callback
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

MappingType = Dict[str, Dict[str, str]]


@dataclass
class SourceInfo:
    """Media Tree structure."""

    entity_id: str
    name: str
    source: str
    source_list: Dict[str, Optional['SourceInfo']]


def _get_sources(attributes: Dict[str, Any]):
    source = attributes.get(ATTR_INPUT_SOURCE)
    sources = list(attributes.get(ATTR_INPUT_SOURCE_LIST, []))
    if source and source not in sources:
        sources.append(source)
    return sources


def _flatten_source(tree: SourceInfo):
    source = tree.source
    if not source:
        return tree.name

    child = tree.source_list.get(source)
    if child:
        return _flatten_source(child)
    else:
        return f"{tree.name}: {source}"


def _flatten_source_list(tree: SourceInfo):
    if not tree.source_list:
        yield tree.name

    for source, value in tree.source_list.items():
        if value:
            yield from _flatten_source_list(value)
        else:
            yield f"{tree.name}: {source}"


def _get_source_tree(hass, mappings: MappingType, entity_id: str, parents: set) -> Optional[SourceInfo]:
    state = hass.states.get(entity_id)
    if state is None:
        return None

    parents = set(parents)
    parents.add(entity_id)

    result: Dict[str, Optional['SourceInfo']] = {}
    mapping = mappings.get(entity_id, {})
    for source in _get_sources(state.attributes):
        result[source] = None

        source_entity_id = mapping.get(source)
        if not source_entity_id:
            continue

        if source_entity_id in parents:
            _LOGGER.debug(
                "Ignoring recursive loop: %s %s %s", entity_id, source, source_entity_id
            )
            continue

        result[source] = _get_source_tree(hass, mappings, source_entity_id, parents)

    return SourceInfo(
        entity_id=state.entity_id,
        name=state.name,
        source=state.attributes.get(ATTR_INPUT_SOURCE),
        source_list=result,
    )


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the universal media players."""
    player = MediaStack(config)

    async_add_entities([player])


class MediaStack(MediaPlayerDevice):
    """Representation of an universal media player."""

    _mapping: MappingType
    _tree: Optional[SourceInfo] = None
    _name: str

    def __init__(self, config):
        """Initialize player."""
        self._mapping = config[CONF_MAPPING]
        self._name = config[CONF_NAME]

    async def async_added_to_hass(self):
        """Subscribe to children."""

        @callback
        def async_on_dependency_update(*_):
            """Update ha state when dependencies update."""
            self.async_schedule_update_ha_state(True)

        entities = []
        for key, value in self._mapping.items():
            entities.append(key)
            for source_entity_id in value.values():
                entities.append(source_entity_id)

        self.async_on_remove(
            self.hass.helpers.event.async_track_state_change(
                entities, async_on_dependency_update
            )
        )

    @property
    def name(self):
        """Return the name of universal player."""
        return self._name

    @property
    def _source_entity(self):
        def _flatten(tree):
            source = tree.source
            child = tree.source_list.get(source)
            if child:
                return _flatten(child)
            else:
                return self.hass.states.get(tree.entity_id)

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
        source_entity = self._source_entity
        sink_entity = self._sink_entity
        if sink_entity is None or sink_entity.state in OFF_STATES:
            return STATE_OFF

        if source_entity is None:
            return sink_entity.state

        if source_entity.state in OFF_STATES:
            return STATE_IDLE
        else:
            return source_entity.state

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
            return list(sorted(_flatten_source_list(self._tree)))
        else:
            return None

    async def _async_call_service(self, state, service_name, service_data=None):
        """Call service on source."""
        if service_data is None:
            service_data = {}

        if state is None:
            raise Exception("Unkown target entity")

        service_data[ATTR_ENTITY_ID] = state.entity_id

        await self.hass.services.async_call(
            DOMAIN, service_name, service_data, blocking=True
        )

    async def _async_call_source(self, service_name, service_data=None):
        await self._async_call_service(self._source_entity, service_name, service_data)

    async def _async_call_sink(self, service_name, service_data=None):
        await self._async_call_service(self._sink_entity, service_name, service_data)

    async def async_turn_on(self):
        """Turn the media player on."""
        await self._async_call_source(SERVICE_TURN_ON)

    async def async_turn_off(self):
        """Turn the media player off."""
        await self._async_call_source(SERVICE_TURN_OFF)

    async def async_mute_volume(self, mute):
        """Mute the volume."""
        data = {ATTR_MEDIA_VOLUME_MUTED: mute}
        await self._async_call_sink(SERVICE_VOLUME_MUTE, data)

    async def async_set_volume_level(self, volume):
        """Set volume level, range 0..1."""
        data = {ATTR_MEDIA_VOLUME_LEVEL: volume}
        await self._async_call_sink(SERVICE_VOLUME_SET, data)

    async def async_media_play(self):
        """Send play command."""
        await self._async_call_source(SERVICE_MEDIA_PLAY)

    async def async_media_pause(self):
        """Send pause command."""
        await self._async_call_source(SERVICE_MEDIA_PAUSE)

    async def async_media_stop(self):
        """Send stop command."""
        await self._async_call_source(SERVICE_MEDIA_STOP)

    async def async_media_previous_track(self):
        """Send previous track command."""
        await self._async_call_source(SERVICE_MEDIA_PREVIOUS_TRACK)

    async def async_media_next_track(self):
        """Send next track command."""
        await self._async_call_source(SERVICE_MEDIA_NEXT_TRACK)

    async def async_media_seek(self, position):
        """Send seek command."""
        data = {ATTR_MEDIA_SEEK_POSITION: position}
        await self._async_call_source(SERVICE_MEDIA_SEEK, data)

    async def async_play_media(self, media_type, media_id, **kwargs):
        """Play a piece of media."""
        data = {ATTR_MEDIA_CONTENT_TYPE: media_type, ATTR_MEDIA_CONTENT_ID: media_id}
        await self._async_call_source(SERVICE_PLAY_MEDIA, data)

    async def async_volume_up(self):
        """Turn volume up for media player."""
        await self._async_call_sink(SERVICE_VOLUME_UP)

    async def async_volume_down(self):
        """Turn volume down for media player."""
        await self._async_call_sink(SERVICE_VOLUME_DOWN)

    async def async_media_play_pause(self):
        """Play or pause the media player."""
        await self._async_call_source(SERVICE_MEDIA_PLAY_PAUSE)

    async def async_select_source(self, source):
        """Set the input source."""
        raise NotImplementedError()

    async def async_clear_playlist(self):
        """Clear players playlist."""
        await self._async_call_source(SERVICE_CLEAR_PLAYLIST)

    async def async_set_shuffle(self, shuffle):
        """Enable/disable shuffling."""
        data = {ATTR_MEDIA_SHUFFLE: shuffle}
        await self._async_call_source(SERVICE_SHUFFLE_SET, data)

    async def async_update(self):
        """Update state in HA."""
        state = self._sink_entity
        if state:
            self._tree = _get_source_tree(
                self.hass, self._mapping, state.entity_id, set()
            )
        else:
            self._tree = None
