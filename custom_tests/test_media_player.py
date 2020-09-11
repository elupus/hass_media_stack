import pytest

from attr import attributes
from homeassistant.helpers.typing import HomeAssistantType
from homeassistant.setup import async_setup_component

from tests.common import assert_setup_component

MOCK_TV_ATTRIBUTES = {
    "supported_features": 0,
}

MOCK_TV_SOURCE_LIST = [
    "HDMI 1",
    "HDMI 2",
    "HDMI 3",
    "Channels",
]

MOCK_STEREO_ATTRIBUTES = {
    "supported_features": 0,
}

MOCK_STEREO_SOURCE_LIST = [
    "AUX",
    "PVR",
    "DISPLAY",
    "CD",
]

MOCK_PVR_ATTRIBUTES = {
    "supported_features": 0,
}

MOCK_PVR_SOURCE_LIST = ["BBC", "Al Jazeera", "Cartoon Network"]

MOCK_CONFIG = {
    "platform": "media_stack",
    "name": "Media Stack",
    "mapping": {
        "media_player.stereo": {
            "DISPLAY": "media_player.tv",
            "GAME": "media_player.playstation",
        },
        "media_player.tv": {
            "HDMI 1": "media_player.stereo",
            "HDMI 3": "media_player.pvr",
        },
    },
}


@pytest.fixture(name="media_stack")
async def media_stack_fixture(hass):
    assert await async_setup_component(
        hass, "media_player", {"media_player": [MOCK_CONFIG]},
    )
    await hass.async_block_till_done()


async def set_and_get(hass, entity_id, state, attributes):
    hass.states.async_set(entity_id, state, attributes)
    await hass.async_block_till_done()
    return hass.states.get("media_player.media_stack")


async def test_missing_entities(hass: HomeAssistantType, media_stack):
    state = hass.states.get("media_player.media_stack")
    assert state.state == "standby"


async def test_missing_source_and_list(hass: HomeAssistantType, media_stack):
    state = await set_and_get(hass, "media_player.tv", "on", MOCK_TV_ATTRIBUTES)
    assert state.state == "on"
    assert state.attributes.get("source") == "tv"


@pytest.mark.xfail(reason="Not working as expected yet")
async def test_missing_source_but_list(hass: HomeAssistantType, media_stack):
    state = await set_and_get(
        hass,
        "media_player.tv",
        "on",
        {**MOCK_TV_ATTRIBUTES, "source_list": MOCK_TV_SOURCE_LIST},
    )
    assert state.state == "on"
    assert state.attributes.get("source") == "tv"


async def test_tv_only(hass: HomeAssistantType, media_stack):
    state = await set_and_get(
        hass,
        "media_player.tv",
        "on",
        {**MOCK_TV_ATTRIBUTES, "source_list": MOCK_TV_SOURCE_LIST, "source": "HDMI 3"},
    )
    assert state.state == "on"
    assert state.attributes.get("source") == "tv: HDMI 3"
    assert state.attributes.get("source_entity_id") == "media_player.tv"
    assert state.attributes.get("sink_entity_id") == "media_player.tv"

    state = await set_and_get(
        hass,
        "media_player.pvr",
        "on",
        {
            **MOCK_STEREO_ATTRIBUTES,
            "source_list": MOCK_PVR_SOURCE_LIST,
            "source": "BBC",
        },
    )
    assert state.state == "on"
    assert state.attributes.get("source") == "pvr: BBC"
    assert state.attributes.get("source_entity_id") == "media_player.pvr"
    assert state.attributes.get("sink_entity_id") == "media_player.tv"

async def test_stereo_only(hass: HomeAssistantType, media_stack):
    state = await set_and_get(
        hass,
        "media_player.stereo",
        "on",
        {
            **MOCK_STEREO_ATTRIBUTES,
            "source_list": MOCK_STEREO_SOURCE_LIST,
            "source": "PVR",
        },
    )
    assert state.state == "on"
    assert state.attributes.get("source") == "stereo: PVR"


async def test_stereo_and_tv(hass: HomeAssistantType, media_stack):
    state = await set_and_get(
        hass,
        "media_player.stereo",
        "on",
        {
            **MOCK_STEREO_ATTRIBUTES,
            "source_list": MOCK_STEREO_SOURCE_LIST,
            "source": "DISPLAY",
        },
    )
    assert state.state == "on"
    assert state.attributes.get("source") == "stereo: DISPLAY"
    assert state.attributes.get("source_entity_id") == "media_player.stereo"
    assert state.attributes.get("sink_entity_id") == "media_player.stereo"

    state = await set_and_get(
        hass,
        "media_player.tv",
        "on",
        {
            **MOCK_STEREO_ATTRIBUTES,
            "source_list": MOCK_TV_SOURCE_LIST,
            "source": "Channels",
        },
    )
    assert state.state == "on"
    assert state.attributes.get("source") == "tv: Channels"
    assert state.attributes.get("source_entity_id") == "media_player.tv"
    assert state.attributes.get("sink_entity_id") == "media_player.stereo"

    state = await set_and_get(
        hass,
        "media_player.tv",
        "on",
        {
            **MOCK_STEREO_ATTRIBUTES,
            "source_list": MOCK_STEREO_SOURCE_LIST,
            "source": "HDMI 3",
        },
    )
    assert state.state == "on"
    assert state.attributes.get("source") == "tv: HDMI 3"
    assert state.attributes.get("source_entity_id") == "media_player.tv"
    assert state.attributes.get("sink_entity_id") == "media_player.stereo"

    state = await set_and_get(
        hass,
        "media_player.pvr",
        "on",
        {
            **MOCK_STEREO_ATTRIBUTES,
            "source_list": MOCK_PVR_SOURCE_LIST,
            "source": "BBC",
        },
    )
    assert state.state == "on"
    assert state.attributes.get("source") == "pvr: BBC"
    assert state.attributes.get("source_entity_id") == "media_player.pvr"
    assert state.attributes.get("sink_entity_id") == "media_player.stereo"


async def test_stereo_and_tv_playstation(hass: HomeAssistantType, media_stack):

    state = await set_and_get(
        hass,
        "media_player.tv",
        "on",
        {
            **MOCK_STEREO_ATTRIBUTES,
            "source_list": MOCK_TV_SOURCE_LIST,
            "source": "HDMI 1",
        },
    )

    state = await set_and_get(
        hass,
        "media_player.stereo",
        "on",
        {
            **MOCK_STEREO_ATTRIBUTES,
            "source_list": MOCK_STEREO_SOURCE_LIST,
            "source": "GAME",
        },
    )

    state = await set_and_get(
        hass,
        "media_player.playstation",
        "off",
        {
            **MOCK_STEREO_ATTRIBUTES,
        },
    )

    assert state.state == "standby"
    assert state.attributes.get("source") == "playstation"
    assert state.attributes.get("source_entity_id") == "media_player.playstation"
    assert state.attributes.get("sink_entity_id") == "media_player.stereo"


async def test_loop(hass: HomeAssistantType, media_stack):
    """Verify that we stop on loops."""
    state = await set_and_get(
        hass,
        "media_player.stereo",
        "on",
        {
            **MOCK_STEREO_ATTRIBUTES,
            "source_list": MOCK_STEREO_SOURCE_LIST,
            "source": "DISPLAY",
        },
    )
    assert state.state == "on"
    assert state.attributes.get("source") == "stereo: DISPLAY"

    state = await set_and_get(
        hass,
        "media_player.tv",
        "on",
        {
            **MOCK_STEREO_ATTRIBUTES,
            "source_list": MOCK_TV_SOURCE_LIST,
            "source": "HDMI 1",
        },
    )
    assert state.state == "on"
    assert state.attributes.get("source") == "tv: HDMI 1"