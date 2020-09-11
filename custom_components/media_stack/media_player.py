"""Media Stack."""
import logging
from typing import Dict, Any, List, Optional, Generator, Set
import voluptuous as vol
import asyncio
from dataclasses import dataclass

from homeassistant.components.media_player import (
    ATTR_MEDIA_SEEK_POSITION,
    ATTR_MEDIA_VOLUME_LEVEL,
    ATTR_MEDIA_VOLUME_MUTED,
    ATTR_TO_PROPERTY,
    DOMAIN,
    PLATFORM_SCHEMA,
    MediaPlayerEntity,
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
    SERVICE_SELECT_SOURCE,
    SUPPORT_SELECT_SOURCE,
    SUPPORT_BROWSE_MEDIA,
    SUPPORT_PLAY_MEDIA,
    SUPPORT_VOLUME_MUTE,
    SUPPORT_VOLUME_SET,
    SUPPORT_VOLUME_STEP,
)
from homeassistant.components.media_player.errors import BrowseError

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
    STATE_STANDBY,
    STATE_OFF,
    STATE_UNAVAILABLE,
)
from homeassistant.core import State, callback
from homeassistant.helpers import config_validation as cv
from voluptuous.schema_builder import Self

_LOGGER = logging.getLogger(__name__)

CONF_MAPPING = "mapping"

OFF_STATES = [STATE_OFF, STATE_STANDBY, STATE_UNAVAILABLE]

SUPPORTED_ANY = SUPPORT_BROWSE_MEDIA | SUPPORT_PLAY_MEDIA
SUPPORTED_SINK = SUPPORT_VOLUME_MUTE | SUPPORT_VOLUME_SET | SUPPORT_VOLUME_STEP

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_MAPPING): {cv.entity_id: {str: cv.entity_id}},
    },
)

MappingType = Dict[str, Dict[str, str]]


@dataclass
class SourceInfo:
    """sfsf."""

    parent: "SourceInfo"
    entity_name: str
    entity_id: str
    source: str
    active: bool

    @property
    def name(self):
        """Name of source."""
        if self.source:
            return f"{self.entity_name}: {self.source}"
        else:
            return f"{self.entity_name}"


def _get_parents(info: SourceInfo) -> Generator[SourceInfo, None, None]:
    while info:
        yield info
        info = info.parent


def _get_root_sources(
    hass, mappings: MappingType, state: State, parent: SourceInfo
) -> Generator[SourceInfo, None, None]:
    if state is None:
        return

    parents = set(x.entity_id for x in _get_parents(parent))
    mapping = mappings.get(state.entity_id, {})
    current = state.attributes.get(ATTR_INPUT_SOURCE)
    sources = _get_sources(state.attributes)
    active = parent is None or parent.active
    if not sources:
        yield SourceInfo(
            entity_id=state.entity_id,
            entity_name=state.name,
            source=current,
            parent=parent,
            active=active,
        )
        return

    for source in sources:
        info = SourceInfo(
            entity_id=state.entity_id,
            entity_name=state.name,
            source=source,
            parent=parent,
            active=active and (current == source),
        )

        source_entity_id = mapping.get(source)
        if not source_entity_id or source_entity_id in parents:
            yield info
            continue

        source_state = hass.states.get(source_entity_id)
        if not source_state:
            yield info
            continue

        yield from _get_root_sources(hass, mappings, source_state, info)


def _get_sources(attributes: Dict[str, Any]) -> List[str]:
    source = attributes.get(ATTR_INPUT_SOURCE)
    sources = list(attributes.get(ATTR_INPUT_SOURCE_LIST, []))
    if source and source not in sources:
        sources.append(source)
    return sources


def _all_entities(mapping: Dict[str, Dict[str, str]]) -> Set[str]:
    entities = set()
    for entity_id, linked_entity_ids in mapping.items():
        entities.add(entity_id)
        for linked_entity_id in linked_entity_ids.values():
            entities.add(linked_entity_id)
    return entities


async def _switch_source(hass, entity_id: str, source: Optional[str]) -> None:
    state = hass.states.get(entity_id)
    if state.state == STATE_OFF:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: entity_id},
            blocking=True,
        )

    if state.attributes.get(ATTR_INPUT_SOURCE) != source:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SELECT_SOURCE,
            {ATTR_ENTITY_ID: entity_id, ATTR_INPUT_SOURCE: source},
            blocking=True,
        )


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the universal media players."""
    player = MediaStack(config)

    async_add_entities([player])


class MediaStack(MediaPlayerEntity):
    """Representation of an universal media player."""

    _mapping: MappingType
    _sources: List[SourceInfo] = []
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
        entity_id = next((x.entity_id for x in self._sources if x.active), None)
        if entity_id:
            return self.hass.states.get(entity_id)
        else:
            return None

    @property
    def _sink_entity(self):
        for entity_id in self._mapping:
            state = self.hass.states.get(entity_id)
            if state and state.state not in OFF_STATES:
                return state

        entity_id = next(iter(self._mapping), None)
        if entity_id:
            return self.hass.states.get(entity_id)
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
            return STATE_STANDBY

        if source_entity is None:
            return sink_entity.state

        if source_entity.state in OFF_STATES:
            return STATE_STANDBY
        else:
            return source_entity.state

    @property
    def source(self):
        """Return the current source of the media player."""
        return next((x.name for x in self._sources if x.active), None)

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

        if self._source_entity:
            attrs["source_entity_id"] = self._source_entity.entity_id
        if self._sink_entity:
            attrs["sink_entity_id"] = self._sink_entity.entity_id

        return attrs

    @property
    def supported_features(self):
        """Return the current state of the media player."""
        supported = self._get_attribute(self._source_entity, ATTR_SUPPORTED_FEATURES, 0)

        supported |= SUPPORT_SELECT_SOURCE

        supported &= ~SUPPORTED_SINK
        supported |= (
            self._get_attribute(self._sink_entity, ATTR_SUPPORTED_FEATURES, 0)
            & SUPPORTED_SINK
        )

        supported_any = 0
        for entity_id in _all_entities(self._mapping):
            state = self.hass.states.get(entity_id)
            supported_any |= self._get_attribute(state, ATTR_SUPPORTED_FEATURES, 0)

        supported &= ~SUPPORTED_ANY
        supported |= supported_any & SUPPORTED_ANY

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
        return list(sorted([x.name for x in self._sources]))

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
        await asyncio.gather(
            *[
                self.hass.services.async_call(
                    DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: entity_id}, blocking=True
                )
                for entity_id in _all_entities(self._mapping)
            ]
        )

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
        entity_id, _, sub_id = media_id.partition(":")
        if entity_id == self.entity_id:
            return

        info = next((x for x in self._sources if x.entity_id == entity_id), None)
        if not info:
            raise KeyError(f"Unable to find {entity_id} in source chain")

        await asyncio.gather(
            *[
                _switch_source(self.hass, x.entity_id, x.source)
                for x in _get_parents(info)
            ]
        )

        component = self.hass.data[DOMAIN]
        player: MediaPlayerEntity = component.get_entity(entity_id)
        if player is None:
            raise Exception(f"Unable to find entity_id {entity_id}")

        await player.async_play_media(media_type, sub_id, **kwargs)

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
        info = next((x for x in self._sources if x.name == source), None)
        if not info:
            raise KeyError(f"Unable to find {source}")

        await asyncio.gather(
            *[
                _switch_source(self.hass, x.entity_id, x.source)
                for x in _get_parents(info)
            ]
        )

    async def async_clear_playlist(self):
        """Clear players playlist."""
        await self._async_call_source(SERVICE_CLEAR_PLAYLIST)

    async def async_set_shuffle(self, shuffle):
        """Enable/disable shuffling."""
        data = {ATTR_MEDIA_SHUFFLE: shuffle}
        await self._async_call_source(SERVICE_SHUFFLE_SET, data)

    async def async_update(self):
        """Update state in HA."""
        self._sources = list(
            _get_root_sources(self.hass, self._mapping, self._sink_entity, None)
        )

    async def _async_browse_media_root(self):
        sources = []
        for entity_id in _all_entities(self._mapping):
            state = self.hass.states.get(entity_id)
            if (
                self._get_attribute(state, ATTR_SUPPORTED_FEATURES)
                & SUPPORT_BROWSE_MEDIA
            ):
                sources.append(
                    {
                        "title": state.name,
                        "media_content_id": entity_id,
                        "media_content_type": "library",
                        "can_play": False,
                        "can_expand": True,
                        "childres": [],
                    }
                )

        root = {
            "title": self.name,
            "media_content_id": self.entity_id,
            "media_content_type": "library",
            "can_play": False,
            "children": sources,
        }

        return root

    async def _async_browse_media_source(
        self, entity_id, media_content_type=None, media_content_id=None
    ):
        component = self.hass.data[DOMAIN]
        player: MediaPlayerEntity = component.get_entity(entity_id)
        if player is None:
            raise BrowseError(f"Unable to find entity_id {entity_id}")

        result = await player.async_browse_media(media_content_type, media_content_id)

        def _add_prefix(data):
            copy = dict(data)
            copy["media_content_id"] = f"{entity_id}:{data['media_content_id']}"
            if "children" in data:
                copy["children"] = [_add_prefix(child) for child in data["children"]]
            return copy

        return _add_prefix(result)

    async def async_browse_media(self, media_content_type=None, media_content_id=None):
        """Implement the websocket media browsing helper."""
        if media_content_id in (None, self.entity_id):
            return await self._async_browse_media_root()
        else:
            entity_id, _, media_content_id = media_content_id.partition(":")
            if media_content_id == "":
                media_content_id = None
                media_content_type = None
            return await self._async_browse_media_source(
                entity_id, media_content_type, media_content_id
            )
