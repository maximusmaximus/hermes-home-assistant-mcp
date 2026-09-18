# Home Assistant MCP Assist Tools Reference

Home Assistant's Model Context Protocol server exposes 20 Assist tools:

### 1. `homeassistant__GetLiveContext`
- **Purpose**: Provides real-time information about the CURRENT state, value, or mode of devices, sensors, entities, or areas.
- **Arguments**:
  - `name` (string, optional): Entity name filter.
  - `domain` (string, optional): Domain filter (e.g. `light`, `switch`, `sensor`, `media_player`, `todo`).
  - `area` (string, optional): Area filter (e.g. `Kitchen`, `Living Room`, `Bedroom`).

### 2. `intent__HassTurnOn` / `intent__HassTurnOff`
- **Purpose**: Turns on/opens/presses or turns off/closes/unlocks a device.
- **Arguments**:
  - `name` (string): Target entity name.
  - `area` (string, optional): Area name.
  - `device_class` (string, optional): Device class filter.

### 3. `light__HassLightSet`
- **Purpose**: Sets brightness percentage or color.
- **Arguments**:
  - `name` (string): Target light name.
  - `brightness` (integer, optional): Brightness percentage (0-100).
  - `color` (string, optional): Color name or hex code.

### 4. `todo__*`
- `todo__get_items`: Query items on a list (filters: `needs_action`, `completed`, `all`).
- `todo__HassListAddItem`: Add task/item.
- `todo__HassListCompleteItem`: Mark item done.
- `todo__HassListRemoveItem`: Delete item.
