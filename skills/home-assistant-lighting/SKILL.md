---
name: home-assistant-lighting
description: Best practices and precision operational guidelines for controlling Home Assistant lights via MCP.
---

# Home Assistant Lighting Operations Skill

Use this skill when controlling, restoring, fading, or adjusting Home Assistant lights and lighting groups via MCP.

## 1. Snapshot Before Bulk Changes, Verify After
1. Call `homeassistant__GetLiveContext` with `domain: "light"` BEFORE any bulk action, and retain the full name, state, and brightness attributes. This snapshot is the authoritative baseline for state restoration.
2. Actuate devices using `intent__HassTurnOn` / `intent__HassTurnOff` or `light__HassLightSet`.
3. Re-run `homeassistant__GetLiveContext` and diff against the snapshot. A tool execution success response confirms the command was sent, but only the subsequent state read verifies physical execution.

## 2. Pitfall: Group Brightness Propagates to All Members
Calling `light__HassLightSet` with `brightness` on a light GROUP entity (e.g. `light.all_presence_lights`) propagates brightness to EVERY member AND TURNS THEM ON.
- Before calling `light__HassLightSet` on an entity name, verify whether that name represents a group.
- If you only want to change specific fixture levels, address individual member fixtures rather than the group.
- If adjusting a group brightness is unavoidable, snapshot the states first, then verify and turn off any member fixtures that were originally off.

## 3. Pitfall: Brightness Units Differ (0-255 vs 0-100%)
- Live Context / Entity State reports `attributes.brightness` on a `0-255` scale.
- `light__HassLightSet` accepts `brightness` as a percentage on a `0-100` scale.
- Convert with: `percent = round(value / 2.55)`.
- Expect minor rounding drift (e.g., 145 vs 146) which represents normal integer rounding rather than state drift.

## 4. Pitfall: Unavailable Entities
An entity reporting state `unavailable` (offline or unpowered fixture) may accept tool commands without returning an explicit error, but will not change state. Never report unavailable fixtures as "turned on". Explicitly flag them as offline or unavailable.

## 5. Pitfall: Missing Transition / Duration Parameter
In the official Home Assistant MCP Assist tool schema, `light__HassLightSet` accepts `brightness`, `color`, and `temperature`, but does NOT support a `transition` parameter. Automated smooth fades cannot be executed in a single MCP tool call.
- To execute a gradual lighting change, use a staged step-down descent across multiple calls or trigger a native Home Assistant script configured with `transition`.

## 6. Staged Descent Pacing
- Write to individual fixtures, never the group.
- Step down progressively: e.g. 100% -> 70% -> 40% -> 20% -> Target.
- Due to MCP HTTP call latency (~1-2 seconds per call), staggered calls create a smooth, natural dimming effect.
- Terminate at the target level without jumping directly to `turn_off`.

## 7. Reporting Standards
- Always report verified counts and states from the post-action context read.
- Clearly identify any lights that failed to respond or remain unavailable.
