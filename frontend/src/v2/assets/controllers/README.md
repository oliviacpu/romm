# Controller artwork

Local SVG front views for the RomM + Sunshine mapping editor. Button locations
in `components/Settings/controllerArtwork.ts` use each SVG's 64-unit coordinate
system. Shoulder/rear controls use labeled callouts above the front view.
Console/emulator functions such as Master System Pause and N64 C-buttons mode
have no invented physical button.

## Controllercons

The following outlines are by **Kieran McClung**, from
[Controllercons 2.1](https://controllercons.github.io/), source revision
`384ac8a1b22b6c173d4a44447df6d73ee96d0427`:

- Xbox Wireless Controller (Series X|S), Xbox Controller S
- DualShock / DualShock 2 (shared DualShock contour)
- Nintendo GameCube, Nintendo 64, NES, Super NES
- Dreamcast HKT-7700, Sega Master System Control Pad

Source: [`versions/2.1/svg/outline`](https://github.com/controllercons/controllercons.github.io/tree/384ac8a1b22b6c173d4a44447df6d73ee96d0427/versions/2.1/svg/outline).
Original contours are preserved, with Xbox Series hybrid D-pad facets added.
Classes were removed and paths wrapped
in an addressable `art` group with `currentColor` for both themes. These assets
remain under the **SIL Open Font License 1.1**. The complete copyright and
license notice is in `CONTROLLERCONS-LICENSE.txt`.

## Original line drawings

These SVGs are original simplified front-view line drawings, licensed
AGPL-3.0-only with RomM. Reference photographs were inspected for contours,
button arrangement, screens, and model distinctions. No photographs are
embedded or redistributed. These are illustrations, not manufacturing drawings.

| File                     | Hardware reference                                                                                                     |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------- |
| `game-boy.svg`           | [Game Boy DMG-01, Evan-Amos](https://commons.wikimedia.org/wiki/File:Game-Boy-FL.jpg)                                  |
| `game-boy-color.svg`     | [Game Boy Color CGB-001, Evan-Amos](https://commons.wikimedia.org/wiki/File:Nintendo-Game-Boy-Color-FL.jpg)            |
| `game-boy-advance.svg`   | [Game Boy Advance AGB-001, Evan-Amos](https://commons.wikimedia.org/wiki/File:Nintendo-Game-Boy-Advance-Purple-FL.jpg) |
| `game-gear.svg`          | [Game Gear HGG-3200, Evan-Amos](https://commons.wikimedia.org/wiki/File:Game-Gear-Handheld.jpg)                        |
| `ds-lite.svg`            | [Nintendo DS Lite USG-001, Evan-Amos](https://commons.wikimedia.org/wiki/File:Nintendo-DS-Lite-Black-Open.jpg)         |
| `genesis-six-button.svg` | [Sega MK-1653, front photograph](https://www.thevideogamecompany.com/collections/sega)                                 |

The DS Lite reference photograph is CC BY-SA 3.0. The other Evan-Amos reference
photographs above are public domain. These references informed new flattened
hardware illustrations. No pixels, textures, or photographic composition were
copied. Product marks and names belong to their respective owners.
