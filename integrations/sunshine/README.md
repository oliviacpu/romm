# Sunshine profiles

RomM owns controller and video profiles. Aurora launches the existing Sunshine
game cards. The launcher resolves a game's profile before starting its emulator:
platform defaults first, then game overrides. Changes take effect on the next
launch, including launches from clients other than Aurora.

In RomM v2, open **Settings → Administration → Streaming → RomM + Sunshine**.
Choose a platform or a game, edit its mappings and video options, then save.
Choosing a physical button swaps its previous assignment. Clearing overrides
restores inheritance after saving. Platform and game selections remain in the URL.
Xbox Series and console controller outlines show the current configured button
assignments in both directions. The schematic changes with the selected platform
and updates while editing. Stick movement retains the emulator's existing axes.

The launcher retains the last 30 sessions, with up to 40 messages each. Messages
include their emulator or Sunshine source and remain available after the game
closes. The interface refreshes while visible. This history captures stdout and
stderr warnings and OSD messages; it does not scrape pixels or replace full logs.
PCSX2 messages default to 200% size. RetroArch uses a larger message font.

## Supported adapters

| Emulator        | Buttons                  | Rendering resolution               | Aspect ratio                                          |
| --------------- | ------------------------ | ---------------------------------- | ----------------------------------------------------- |
| PCSX2           | Native pad configuration | Native, 720p, 1080p, 1440p presets | Original, automatic widescreen patches, explicit 16:9 |
| Dolphin         | Native pad configuration | Native, 720p, 1080p, 1440p presets | Original or 16:9 for games with native support        |
| Flycast         | SDL controller mapping   | 480p, 720p, 1080p, 1440p           | Original or widescreen hack, selected per game        |
| xemu            | SDL controller mapping   | Native, 720p, 1080p, 1440p presets | Automatic game aspect or explicit 16:9                |
| RetroArch cores | Core remap file          | Existing core settings             | Existing core settings                                |

Resolution presets are approximate for games with different native heights.
They change emulator rendering; choose streaming resolution and bitrate in
Aurora. A higher rendering resolution does not make an unsupported game widescreen.
PCSX2's automatic option applies available bundled patches and lets each patch
select its aspect ratio. Forced widescreen may cause stretched images or culling
artifacts. Dolphin's original setting uses automatic game-aspect detection, including native widescreen selected inside a game. Its generic widescreen hack remains off.

RetroArch keeps frontend input bindings fixed and generates core remaps, so game
overrides do not change menu confirmation or cancellation. Nintendo face buttons
default to matching Xbox labels; N64 A and B default to Xbox A and B. Game menu
conventions can still differ. Triggers can be swapped with one another while
retaining analog input. Stick axes remain at their existing mappings.

Menu and quit shortcuts are configurable in the same platform and game profiles.
Menu defaults to both stick clicks; quit defaults to left stick click + Menu held
for two seconds. Choices include Share, Xbox/Guide, both shoulders, and View + Y.
They use physical buttons independently of game mappings. Every platform opens the
same host-rendered session menu inside the Sunshine stream. D-pad moves, Xbox A
confirms, and Xbox B goes back. The menu includes resume, controller assignments,
graphics, recent warnings, restart, and quit confirmation. Settings use RomM's
existing profile file and revision lock, with platform defaults and game overrides.
Saving does not restart the game; choose restart explicitly after saving progress.

The menu waits for the opening shortcut to be released, takes exclusive controller
input, then suspends the game. Resume waits for menu buttons to be released before
returning input. A crashed menu releases input and resumes the game. Native emulator
and disc controls remain accessible for PCSX2, RetroArch, Flycast, and xemu; Dolphin's
desktop interface has no controller-operated disc adapter here. The menu runs as the
existing emulator user over the private control socket, without a web port or Docker
access. Apple TV can reserve Xbox/Guide or View + Menu independently.

Share requires Sunshine's `gamepad = xseries` profile and a client that forwards
the button. Aurora forwards it when exposed by tvOS. The installed Sunshine build's
Linux uinput profile exposes Share as `KEY_RECORD`. Physical controller acceptance
must still be checked through the streaming client. The virtual Series profile's
SDL name is `Xbox Series X Controller`; changing profiles also requires updating
xemu's port-one GUID and Dolphin's device identity. Back up these files first.

## Deployment

This adapter targets the supplied custom launcher and the RomM 5.4.1 fork layout.
It does not install emulators or require a Docker socket in RomM. The overlay
Dockerfiles require local base images whose exact image IDs have been recorded.
Tag the recorded bases as `romm-local-base:5.4.1` and
`emulators-local-base:20261029`. Build from the repository root and retain both
previous images for rollback:

```sh
docker build -f integrations/sunshine/Dockerfile.api -t romm-local-api:5.4.1 .
cd frontend
npm run generate
npm run build
cd ..
docker build -f integrations/sunshine/Dockerfile.romm -t romm-local:5.4.1 .
docker build -f integrations/sunshine/Dockerfile.stream -t emulators-local:20261029 .
```

The API image must be running in an isolated development environment when
generating OpenAPI types. Use the configured development API URL for generation.
Do not generate against an older deployed API.

Mount the launcher's `/config/integration` directory into RomM at `/emulation`,
set `ROMM_EMULATION_PATH=/emulation`, and allow RomM's process to write profiles
there. The directory contains only integration JSON, not Sunshine credentials or
pairings. The launcher publishes its catalog and heartbeat there. API access
requires administrator role and the appropriate read or write scope. With no
mount or environment setting, the integration reports itself as unconfigured.

Flycast and xemu remaps use the existing Sunshine SDL baseline in
`/config/pcsx2/PCSX2/game_controller_db.txt`, named `Xbox 360 via Sunshine`.
The adapter also includes the measured Xbox Series baseline for the pinned Linux
uinput profile. It derives raw button and axis bindings from these baselines and passes
the requested mapping through `SDL_GAMECONTROLLERCONFIG`. Existing Flycast
device-specific mappings can override SDL defaults and need individual review.

Before deployment, confirm that no game, connected client, or reconnect grace
period is active. Back up Compose configuration, emulator INIs, integration
profiles, Sunshine pairing, and catalog identities. Recreate only RomM and the
stream container. Verify health, API authentication, unchanged pairings and card
IDs, and persistence of saves. On failure, restore the previous images and INIs.

## Checks

```sh
PYTHONPATH=backend python -m unittest discover -s integrations/sunshine/tests -v
cd backend
python -m unittest tests.endpoints.test_emulation -v
cd ../frontend
npm run typecheck
npx vitest run --project app src/v2/components/Settings/EmulationSection.test.ts
```

These checks cover API access, inheritance, conflicting edits, reversible mapping
swaps, preservation of unrelated INI settings, bounded message history, and fixed
RetroArch menu input. They do not establish performance or controller behavior
on an Apple TV. The native emulator builds must match the adapter's setting names.
