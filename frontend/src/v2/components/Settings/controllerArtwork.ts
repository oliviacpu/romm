import controllerconsLicense from "@/v2/assets/controllers/CONTROLLERCONS-LICENSE.txt?url&no-inline";
import dreamcast from "@/v2/assets/controllers/dreamcast.svg?no-inline";
import ds from "@/v2/assets/controllers/ds-lite.svg?no-inline";
import gba from "@/v2/assets/controllers/game-boy-advance.svg?no-inline";
import gbc from "@/v2/assets/controllers/game-boy-color.svg?no-inline";
import gb from "@/v2/assets/controllers/game-boy.svg?no-inline";
import gamegear from "@/v2/assets/controllers/game-gear.svg?no-inline";
import gc from "@/v2/assets/controllers/gamecube.svg?no-inline";
import genesis from "@/v2/assets/controllers/genesis-six-button.svg?no-inline";
import sms from "@/v2/assets/controllers/master-system.svg?no-inline";
import n64 from "@/v2/assets/controllers/n64.svg?no-inline";
import nes from "@/v2/assets/controllers/nes.svg?no-inline";
import ps from "@/v2/assets/controllers/ps2.svg?no-inline";
import snes from "@/v2/assets/controllers/snes.svg?no-inline";
import xbox from "@/v2/assets/controllers/xbox-controller-s.svg?no-inline";
import series from "@/v2/assets/controllers/xbox-series-x.svg?no-inline";

type Point = readonly [x: number, y: number];
interface Artwork {
  source: string;
  model: string;
  viewBox: string;
  controls: Record<string, Point>;
  marks: Record<string, string>;
  rear?: string[];
  license?: string;
}
const directions = (
  x: number,
  y: number,
  spacing: number,
): Record<string, Point> => ({
  up: [x, y - spacing],
  down: [x, y + spacing],
  left: [x - spacing, y],
  right: [x + spacing, y],
});
const playstation: Artwork = {
  source: ps,
  license: controllerconsLicense,
  model: "DualShock 2",
  viewBox: "-3 -4 70 62",
  controls: {
    a: [50.76, 31.06],
    b: [55.48, 26.35],
    x: [45.85, 26.35],
    y: [50.79, 21.41],
    lb: [13, 8],
    rb: [51, 8],
    lt: [13, 0],
    rt: [51, 0],
    view: [26.33, 26.49],
    menu: [37.65, 26.41],
    l3: [22.58, 35.82],
    r3: [41.09, 35.82],
    ...directions(12.84, 26.38, 3.2),
  },
  marks: {
    a: "×",
    b: "○",
    x: "□",
    y: "△",
    lb: "L1",
    rb: "R1",
    lt: "L2",
    rt: "R2",
  },
  rear: ["lt", "rt"],
};
const sega: Artwork = {
  source: genesis,
  model: "Sega Six Button Control Pad",
  viewBox: "-3 9 70 44",
  controls: {
    x: [40, 33],
    a: [47.5, 30.5],
    b: [55, 28],
    lb: [38, 26],
    y: [45, 24],
    rb: [52, 22],
    menu: [31, 28],
    ...directions(14, 30, 3.5),
  },
  marks: { x: "A", a: "B", b: "C", lb: "X", y: "Y", rb: "Z" },
};
export const controllerArtwork: Record<string, Artwork> = {
  "xbox-series": {
    source: series,
    license: controllerconsLicense,
    model: "Xbox Wireless Controller (Series X|S)",
    viewBox: "-3 -4 70 62",
    controls: {
      a: [48.4, 26.25],
      b: [52.69, 21.98],
      x: [44.09, 21.98],
      y: [48.4, 17.71],
      lb: [16, 8],
      rb: [48, 8],
      lt: [16, 1],
      rt: [48, 1],
      view: [27.38, 21.82],
      menu: [36.7, 21.82],
      share: [32, 25.5],
      guide: [32, 15.44],
      l3: [15.6, 21.9],
      r3: [40.38, 31.47],
      ...directions(23.5, 32.31, 3.2),
    },
    marks: {
      a: "A",
      b: "B",
      x: "X",
      y: "Y",
      lb: "LB",
      rb: "RB",
      lt: "LT",
      rt: "RT",
    },
    rear: ["lt", "rt"],
  },
  ps2: playstation,
  psx: { ...playstation, model: "DualShock" },
  gc: {
    source: gc,
    license: controllerconsLicense,
    model: "Nintendo GameCube Controller",
    viewBox: "-3 0 70 60",
    controls: {
      a: [51.31, 24.04],
      b: [43.98, 27.71],
      x: [58.14, 22.48],
      y: [49.38, 17.31],
      menu: [31.93, 24.46],
      lt: [10, 7],
      rt: [52, 7],
      rb: [59, 7],
      ...directions(21.82, 38.26, 2.8),
    },
    marks: { a: "A", b: "B", x: "X", y: "Y", lt: "L", rt: "R", rb: "Z" },
    rear: ["lt", "rt", "rb"],
  },
  dreamcast: {
    source: dreamcast,
    license: controllerconsLicense,
    model: "Dreamcast Controller (HKT-7700)",
    viewBox: "-3 -8 70 76",
    controls: {
      a: [52.27, 31.32],
      b: [57.75, 25.99],
      x: [46.78, 25.99],
      y: [52.27, 20.65],
      menu: [32, 46.5],
      lt: [9, -3],
      rt: [55, -3],
      ...directions(12.79, 34.77, 3.5),
    },
    marks: { a: "A", b: "B", x: "X", y: "Y", lt: "L", rt: "R" },
    rear: ["lt", "rt"],
  },
  xbox: {
    source: xbox,
    license: controllerconsLicense,
    model: "Xbox Controller S",
    viewBox: "-3 -4 70 66",
    controls: {
      a: [50.13, 27.61],
      b: [55.07, 22.78],
      x: [45.32, 22.78],
      y: [50.13, 17.89],
      lb: [50.83, 35.75],
      rb: [55.71, 31.7],
      view: [7.41, 29.55],
      menu: [11.02, 33.42],
      lt: [14, 1],
      rt: [50, 1],
      l3: [13.78, 22.78],
      r3: [40.72, 33.42],
      ...directions(22.47, 33.32, 3.3),
    },
    marks: { a: "A", b: "B", x: "X", y: "Y", lt: "L", rt: "R" },
    rear: ["lt", "rt"],
  },
  genesis: sega,
  segacd: sega,
  sms: {
    source: sms,
    license: controllerconsLicense,
    model: "Sega Master System Control Pad",
    viewBox: "-3 17 70 32",
    controls: {
      a: [45.1, 35.65],
      b: [55.8, 35.65],
      ...directions(16.9, 32, 4.6),
    },
    marks: { a: "1", b: "2" },
  },
  nes: {
    source: nes,
    license: controllerconsLicense,
    model: "NES Controller (NES-004)",
    viewBox: "-3 17 70 32",
    controls: {
      a: [43.12, 35.98],
      b: [53.13, 35.98],
      view: [25.68, 37.25],
      menu: [32.64, 37.25],
      ...directions(11.95, 33.98, 3.5),
    },
    marks: { a: "B", b: "A" },
  },
  snes: {
    source: snes,
    license: controllerconsLicense,
    model: "Super NES Controller",
    viewBox: "-3 13 70 36",
    controls: {
      a: [50.75, 37.18],
      b: [56.9, 32.35],
      x: [44.53, 32.4],
      y: [50.68, 27.57],
      lb: [13.74, 19.58],
      rb: [50.26, 19.59],
      view: [25.94, 34.61],
      menu: [33.05, 34.61],
      ...directions(13.68, 32.57, 3.8),
    },
    marks: { a: "B", b: "A", x: "Y", y: "X", lb: "L", rb: "R" },
  },
  gb: {
    source: gb,
    model: "Game Boy (DMG-01)",
    viewBox: "12 0 40 64",
    controls: {
      a: [37, 45],
      b: [44, 41.8],
      view: [27.5, 53.5],
      menu: [34, 50.5],
      ...directions(22, 42, 2.5),
    },
    marks: { a: "B", b: "A" },
  },
  gbc: {
    source: gbc,
    model: "Game Boy Color (CGB-001)",
    viewBox: "12 0 40 64",
    controls: {
      a: [37, 43],
      b: [44, 40],
      view: [28.1, 51.7],
      menu: [34.6, 51.7],
      ...directions(22, 41, 2.5),
    },
    marks: { a: "B", b: "A" },
  },
  gba: {
    source: gba,
    model: "Game Boy Advance (AGB-001)",
    viewBox: "-2 9 68 44",
    controls: {
      a: [53, 29.5],
      b: [59, 25],
      view: [8.5, 40.2],
      menu: [8.5, 36],
      lb: [8, 15],
      rb: [56, 15],
      ...directions(8.5, 27, 2.5),
    },
    marks: { a: "B", b: "A", lb: "L", rb: "R" },
  },
  gamegear: {
    source: gamegear,
    model: "Sega Game Gear (HGG-3200)",
    viewBox: "-2 9 68 46",
    controls: {
      a: [52, 35],
      b: [58, 31],
      menu: [53, 24.5],
      ...directions(8.5, 28, 2.5),
    },
    marks: { a: "1", b: "2" },
  },
  nds: {
    source: ds,
    model: "Nintendo DS Lite (USG-001)",
    viewBox: "4 0 56 64",
    controls: {
      a: [50.5, 46],
      b: [54, 42.5],
      x: [47, 42.5],
      y: [50.5, 39],
      menu: [49, 52],
      view: [49, 56],
      lb: [9, 32],
      rb: [55, 32],
      ...directions(13.5, 43, 1.7),
    },
    marks: { a: "B", b: "A", x: "Y", y: "X", lb: "L", rb: "R" },
  },
  n64: {
    source: n64,
    license: controllerconsLicense,
    model: "Nintendo 64 Controller (NUS-005)",
    viewBox: "-3 -7 70 75",
    controls: {
      a: [49.17, 27.23],
      x: [44.48, 22.35],
      b: [58.07, 18.24],
      y: [53.98, 14.36],
      menu: [32, 22.82],
      lb: [12.16, 8.46],
      rb: [51.86, 8.48],
      lt: [32, -2],
      ...directions(11, 20.95, 3.4),
    },
    marks: { a: "A", x: "B", b: "→", y: "↑", lb: "L", rb: "R", lt: "Z" },
    rear: ["lt"],
  },
};
