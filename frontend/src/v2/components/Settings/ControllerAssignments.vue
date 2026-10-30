<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  system: string;
  title: string;
  labels: Record<string, string>;
  assignments: Record<string, string>;
}>();

type Point = [x: number, y: number];
const family = computed(() => {
  if (["psx", "ps2"].includes(props.system)) return "playstation";
  if (["genesis", "segacd"].includes(props.system)) return "genesis";
  if (["gb", "gbc"].includes(props.system)) return "gameboy";
  if (["gba", "gamegear"].includes(props.system)) return "handheld";
  if (["nes", "sms"].includes(props.system)) return "rectangle";
  return props.system;
});

const layouts: Record<string, Record<string, Point>> = {
  playstation: {
    l3: [230, 260],
    r3: [410, 260],
    view: [275, 180],
    menu: [365, 180],
  },
  gc: {
    a: [520, 175],
    b: [465, 235],
    x: [575, 160],
    y: [520, 105],
    rb: [590, 35],
    rt: [480, 25],
    l3: [155, 155],
    r3: [400, 265],
  },
  dreamcast: { menu: [320, 225], l3: [155, 155] },
  n64: {
    a: [460, 245],
    x: [410, 195],
    b: [570, 165],
    y: [520, 110],
    menu: [320, 125],
    l3: [320, 245],
    lt: [320, 25],
    lb: [120, 50],
    rb: [525, 50],
  },
  genesis: {
    x: [450, 220],
    a: [510, 200],
    b: [570, 180],
    lb: [450, 130],
    y: [510, 110],
    rb: [570, 90],
    menu: [320, 165],
  },
  rectangle: {
    a: [455, 185],
    b: [550, 185],
    view: [280, 235],
    menu: [355, 235],
  },
  snes: { view: [280, 205], menu: [355, 205] },
  gameboy: { a: [350, 220], b: [400, 175], view: [285, 300], menu: [385, 300] },
  handheld: {
    a: [475, 205],
    b: [550, 165],
    view: [420, 280],
    menu: [485, 280],
  },
  nds: {
    a: [480, 275],
    b: [530, 235],
    x: [430, 235],
    y: [480, 185],
    view: [445, 350],
    menu: [525, 350],
  },
};

const pins = computed(() => {
  const dpad: Point =
    family.value === "gameboy"
      ? [260, 195]
      : family.value === "nds"
        ? [160, 245]
        : ["gc", "dreamcast", "xbox-series", "xbox"].includes(family.value)
          ? [235, 265]
          : [150, 180];
  const positions: Record<string, Point> = {
    a: [520, 225],
    b: [570, 175],
    x: [470, 175],
    y: [520, 125],
    lt: [110, 25],
    rt: [550, 25],
    lb: [155, 80],
    rb: [465, 70],
    view: [270, 160],
    menu: [370, 160],
    share: [320, 245],
    guide: [320, 100],
    l3: [155, 155],
    r3: [400, 265],
    up: [dpad[0], dpad[1] - 36],
    down: [dpad[0], dpad[1] + 36],
    left: [dpad[0] - 38, dpad[1]],
    right: [dpad[0] + 38, dpad[1]],
    ...layouts[family.value],
  };
  const arrows: Record<string, string> = {
    up: "↑",
    down: "↓",
    left: "←",
    right: "→",
  };
  const marks: Record<string, string> = {
    view: "▱",
    menu: "≡",
    share: "↥",
    guide: "X",
    l3: "L3",
    r3: "R3",
  };
  const symbols: Record<string, string> = {
    Cross: "×",
    Circle: "○",
    Square: "□",
    Triangle: "△",
    "L trigger": "L",
    "R trigger": "R",
    "C-right": "C→",
    "C-up": "C↑",
    "C buttons mode": "C mode",
    "D-pad up": "↑",
    "D-pad down": "↓",
    "D-pad left": "←",
    "D-pad right": "→",
  };
  return Object.entries(props.labels)
    .filter(([, label]) => label !== "C buttons mode")
    .map(([key, label]) => ({
      key,
      label,
      position: positions[key] ?? [320, 320],
      mark:
        arrows[key] ??
        (props.system === "xbox-series"
          ? (marks[key] ?? label)
          : (symbols[label] ??
            (label === "Select" && ["gameboy", "nds"].includes(family.value)
              ? "Sel"
              : label))),
      assignment:
        symbols[props.assignments[key] ?? ""] ?? props.assignments[key] ?? "",
      directional: !!arrows[key],
    }));
});
const description = computed(
  () =>
    `${props.title}: ${pins.value.map((pin) => `${pin.label}: ${pin.assignment}`).join(", ")}`,
);
const sticks = computed(() => {
  if (
    ["gc", "dreamcast", "xbox", "playstation", "n64"].includes(family.value)
  ) {
    return [
      { key: "l3", position: layouts[family.value]?.l3 ?? [155, 155] },
      ...(family.value === "dreamcast" || family.value === "n64"
        ? []
        : [{ key: "r3", position: layouts[family.value]?.r3 ?? [400, 265] }]),
    ].filter((stick) => !(stick.key in props.labels));
  }
  return [];
});
</script>

<template>
  <figure class="controller-assignments">
    <figcaption>{{ title }}</figcaption>
    <svg
      :viewBox="
        family === 'gameboy'
          ? '180 0 300 370'
          : family === 'nds'
            ? '70 0 520 430'
            : '0 0 640 370'
      "
      role="img"
      :aria-label="description"
    >
      <g class="controller-assignments__shell">
        <template v-if="family === 'gameboy'">
          <rect x="210" y="8" width="235" height="348" rx="28" />
          <rect
            class="controller-assignments__screen"
            x="237"
            y="30"
            width="182"
            height="105"
            rx="8"
          />
        </template>
        <template v-else-if="family === 'nds'">
          <rect x="100" y="4" width="455" height="156" rx="22" />
          <rect x="100" y="166" width="455" height="234" rx="22" />
          <rect
            class="controller-assignments__screen"
            x="245"
            y="25"
            width="160"
            height="112"
            rx="6"
          />
          <rect
            class="controller-assignments__screen"
            x="245"
            y="198"
            width="160"
            height="126"
            rx="6"
          />
        </template>
        <template v-else-if="family === 'handheld'">
          <path
            d="M115 80 Q55 90 60 230 Q70 310 160 320 H490 Q580 310 585 230 Q590 90 530 80 Z"
          />
          <rect
            class="controller-assignments__screen"
            x="235"
            y="105"
            width="175"
            height="160"
            rx="8"
          />
        </template>
        <rect
          v-else-if="family === 'rectangle'"
          x="60"
          y="100"
          width="540"
          height="200"
          rx="20"
        />
        <path
          v-else-if="family === 'snes'"
          d="M155 100 H485 C620 70 650 290 510 300 L390 260 H250 L130 300 C-10 290 20 70 155 100 Z"
        />
        <path
          v-else-if="family === 'genesis'"
          d="M130 100 Q320 30 540 65 Q620 95 615 245 Q595 330 520 290 L360 245 H265 L120 305 Q30 300 45 200 Q65 115 130 100 Z"
        />
        <path
          v-else-if="family === 'n64'"
          d="M130 60 Q320 20 525 60 Q580 75 595 160 L615 310 Q610 360 565 330 L470 235 H390 L355 350 Q320 375 285 350 L250 235 H185 L90 330 Q45 360 45 310 L65 160 Q80 75 130 60 Z"
        />
        <template v-else-if="family === 'dreamcast'">
          <path
            d="M125 65 Q320 25 515 65 L600 250 Q620 340 540 320 L405 275 H235 L100 320 Q20 340 40 250 Z"
          />
          <rect
            class="controller-assignments__screen"
            x="275"
            y="100"
            width="90"
            height="100"
            rx="8"
          />
        </template>
        <path
          v-else-if="family === 'gc'"
          d="M130 65 Q320 30 520 65 Q580 90 590 185 L620 320 Q615 365 565 335 L450 265 H200 L85 335 Q35 365 40 320 L70 185 Q70 90 130 65 Z"
        />
        <path
          v-else-if="family === 'playstation'"
          d="M120 75 H520 Q580 90 585 160 L620 310 Q610 370 560 335 L445 270 H195 L80 335 Q30 370 20 310 L55 160 Q60 90 120 75 Z"
        />
        <path
          v-else
          d="M130 65 Q320 25 510 65 Q570 85 585 175 L620 310 Q615 365 565 335 L440 265 H200 L75 335 Q25 365 20 310 L55 175 Q70 85 130 65 Z"
        />
      </g>
      <g class="controller-assignments__sticks" aria-hidden="true">
        <g
          v-for="stick in sticks"
          :key="stick.key"
          :transform="`translate(${stick.position[0]}, ${stick.position[1]})`"
        >
          <circle r="32" />
          <circle r="21" />
        </g>
      </g>
      <g
        v-for="pin in pins"
        :key="pin.key"
        :transform="`translate(${pin.position[0]}, ${pin.position[1]})`"
        :class="[
          'controller-assignments__pin',
          { 'controller-assignments__pin--direction': pin.directional },
        ]"
      >
        <title>{{ pin.label }}: {{ pin.assignment }}</title>
        <circle :r="pin.directional ? 17 : 25" />
        <g
          v-if="system === 'xbox-series' && pin.key === 'view'"
          class="controller-assignments__symbol"
        >
          <rect x="-13" y="-10" width="17" height="14" />
          <rect x="-5" y="-3" width="17" height="14" />
        </g>
        <path
          v-else-if="system === 'xbox-series' && pin.key === 'share'"
          class="controller-assignments__symbol"
          d="M-12 2 V11 H12 V2 M0 5 V-13 M-6 -7 L0 -13 L6 -7"
        />
        <text
          v-else
          class="controller-assignments__button"
          dominant-baseline="central"
          text-anchor="middle"
        >
          {{ pin.mark }}
        </text>
        <text
          v-if="
            pin.assignment && (!pin.directional || pin.assignment !== pin.mark)
          "
          class="controller-assignments__assignment"
          :y="pin.directional ? 29 : 43"
          text-anchor="middle"
        >
          {{ pin.assignment }}
        </text>
      </g>
    </svg>
  </figure>
</template>

<style scoped>
.controller-assignments {
  margin: 0;
  min-width: 0;
}
figcaption {
  font-weight: var(--r-font-weight-semibold);
  padding: var(--r-space-3) 0;
}
svg {
  display: block;
  width: 100%;
  max-height: 370px;
  overflow: visible;
}
.controller-assignments__shell {
  fill: var(--r-color-surface);
  stroke: var(--r-color-border);
  stroke-width: 3;
}
.controller-assignments__screen {
  fill: var(--r-color-bg);
}
.controller-assignments__sticks {
  fill: var(--r-color-bg);
  stroke: var(--r-color-fg-muted);
  stroke-width: 2;
}
.controller-assignments__pin circle {
  fill: var(--r-color-bg);
  stroke: var(--r-color-fg-muted);
  stroke-width: 2;
}
.controller-assignments__button {
  fill: var(--r-color-fg);
  font-size: 26px;
  font-weight: 600;
}
.controller-assignments__symbol {
  fill: none;
  stroke: var(--r-color-fg);
  stroke-width: 2;
}
.controller-assignments__assignment {
  fill: var(--r-color-brand-primary);
  font-size: 26px;
  font-weight: 600;
}
.controller-assignments__pin--direction .controller-assignments__assignment {
  font-size: 18px;
}
</style>
