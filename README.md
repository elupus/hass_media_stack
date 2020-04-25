# Media Stack - An home assistant integration to handle a set of interconnected media_players

The integration will select the first media player in the `mapping` as the sink and it will be the entity that services like volume controls are sent to.

It will follow the selected source of the sink, down to the root selected source media player entity,  which will be considered the media source. It will be the target of services like play/pause/stop. For example `media_player.tv[HDMI 2]` -> `media_player.stereo[PVR]` - > `media_player.bedroom`

## Example Configuration
This example configuration will use the demo sources as root sources.

```yaml
media_player:
  - platform: demo

  - platform: media_stack
    name: My Stack
    mapping:
      media_player.tv:
        "HDMI 1": media_player.lounge_room
        "HDMI 2": media_player.stereo
      media_player.stereo:
        PVR:  media_player.bedroom
        DISPLAY: media_player.philips_tv
        AUX: media_player.walkman
        AV: media_player.living_room
```
