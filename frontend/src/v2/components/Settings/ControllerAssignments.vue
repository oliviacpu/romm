<script setup lang="ts">
import { RBtn } from "@v2/lib";
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { controllerArtwork } from "@/v2/components/Settings/controllerArtwork";

const props = defineProps<{
  system: string;
  title: string;
  labels: Record<string, string>;
  assignments: Record<string, string>;
  selected: string;
  selectable: string[];
  disabled?: boolean;
}>();
const emit = defineEmits<{ select: [key: string] }>();
const { t } = useI18n();
const art = computed(() => controllerArtwork[props.system]);
const entries = computed(() => Object.entries(props.labels));
const selection = computed(() => art.value?.controls[props.selected]);
const selectedLabel = computed(() => props.labels[props.selected] ?? "");
const description = computed(
  () =>
    `${props.title}: ${entries.value.map(([key, label]) => `${label}: ${props.assignments[key] || t("emulation.unassigned")}`).join(", ")}`,
);
const rear = computed(() => art.value?.rear?.includes(props.selected));
const frame = computed(() =>
  (art.value?.viewBox ?? "0 0 64 64").split(" ").map(Number),
);
const marks = computed(() =>
  Object.entries(art.value?.marks ?? {}).flatMap(([key, label]) => {
    const point = art.value?.controls[key];
    return point ? [{ key, label, point }] : [];
  }),
);
const rearCallouts = computed(() =>
  (art.value?.rear ?? [])
    .map((key) => {
      const point = art.value?.controls[key];
      return point ? `M${point[0]} ${point[1] + 2}v3` : "";
    })
    .join(" "),
);
const hitTargets = computed(() =>
  entries.value.flatMap(([key, label]) => {
    const point = art.value?.controls[key];
    return point && props.selectable.includes(key)
      ? [{ key, label, point }]
      : [];
  }),
);
function position(point: readonly [number, number]) {
  const [x = 0, y = 0, width = 64, height = 64] = frame.value;
  return {
    left: `${((point[0] - x) / width) * 100}%`,
    top: `${((point[1] - y) / height) * 100}%`,
  };
}
function displayLabel(key: string, label: string): string {
  const names: Record<string, string> = {
    view: "View",
    menu: "Menu",
    share: "Share",
    guide: "Xbox",
    l3: "L3",
    r3: "R3",
  };
  return props.system === "xbox-series" ? (names[key] ?? label) : label;
}
function enabled(key: string) {
  return !props.disabled && props.selectable.includes(key);
}
</script>

<template>
  <figure class="controller-assignments">
    <figcaption>
      <strong>{{ title }}</strong>
      <span v-if="art">{{ art.model }}</span>
    </figcaption>
    <div
      v-if="art"
      class="controller-assignments__drawing"
      :style="{ aspectRatio: `${frame[2]} / ${frame[3]}` }"
    >
      <svg :viewBox="art.viewBox" role="img" :aria-label="description">
        <use :href="`${art.source}#art`" />
        <g aria-hidden="true" class="controller-assignments__marks">
          <text
            v-for="mark in marks"
            :key="mark.key"
            :x="mark.point[0]"
            :y="mark.point[1]"
            dominant-baseline="central"
          >
            {{ mark.label }}
          </text>
          <template v-if="system === 'xbox-series'">
            <text x="32" y="15.44" dominant-baseline="central">X</text>
            <path
              d="M26.4 21.1h1.2v1h-1.2zM27.1 21.6h1.2v1h-1.2zM35.9 21.2h1.6m-1.6.6h1.6m-1.6.6h1.6M31 25.5v.7h2v-.7m-1-1.1v1.1m-.5-.6.5-.5.5.5"
              fill="none"
              stroke="currentColor"
              stroke-width=".2"
            />
          </template>
          <text
            v-if="system === 'n64'"
            x="50.05"
            y="18.24"
            dominant-baseline="central"
          >
            ←
          </text>
          <text
            v-if="system === 'n64'"
            x="54.23"
            y="22.17"
            dominant-baseline="central"
          >
            ↓
          </text>
          <path
            v-if="art.rear?.length"
            :d="rearCallouts"
            fill="none"
            stroke="currentColor"
            stroke-width=".3"
            stroke-dasharray=".6 .6"
          />
        </g>
        <circle
          v-if="selection"
          class="controller-assignments__selection"
          :cx="selection[0]"
          :cy="selection[1]"
          r="3.2"
          aria-hidden="true"
        />
      </svg>
      <template v-for="{ key, label, point } in hitTargets" :key="key">
        <RBtn
          class="controller-assignments__hit"
          :style="position(point)"
          variant="plain"
          icon
          :aria-label="`${label}: ${assignments[key] || t('emulation.unassigned')}`"
          :disabled="!enabled(key)"
          :active="selected === key"
          @click="emit('select', key)"
        />
      </template>
    </div>
    <div class="controller-assignments__current" aria-live="polite">
      <strong>{{ selectedLabel }}</strong>
      <span aria-hidden="true">→</span>
      <span>{{ assignments[selected] || t("emulation.unassigned") }}</span>
    </div>
    <p v-if="rear" class="controller-assignments__note">
      {{ t("emulation.rear-control") }}
    </p>
    <p
      v-else-if="selectedLabel && !selection"
      class="controller-assignments__note"
    >
      {{ t("emulation.console-function") }}
    </p>
    <div class="controller-assignments__legend">
      <template v-for="[key, label] in entries" :key="key">
        <RBtn
          v-if="selectable.includes(key)"
          variant="text"
          class="controller-assignments__entry"
          :aria-label="`${label}: ${assignments[key] || t('emulation.unassigned')}`"
          :active="selected === key"
          :disabled="!enabled(key)"
          @click="emit('select', key)"
        >
          <span>{{ displayLabel(key, label) }}</span
          ><span aria-hidden="true">→</span
          ><strong>{{ assignments[key] || t("emulation.unassigned") }}</strong>
        </RBtn>
        <div v-else class="controller-assignments__passive">
          <span>{{ displayLabel(key, label) }}</span
          ><span aria-hidden="true">→</span
          ><strong>{{ assignments[key] || t("emulation.unassigned") }}</strong>
        </div>
      </template>
    </div>
  </figure>
</template>

<style scoped>
.controller-assignments {
  min-width: 0;
  margin: 0;
  padding: var(--r-space-4);
  border: 1px solid var(--r-color-border);
  border-radius: var(--r-radius-lg);
}
figcaption {
  display: grid;
  gap: var(--r-space-1);
}
figcaption span,
.controller-assignments__note {
  color: var(--r-color-fg-muted);
  font-size: var(--r-font-size-sm);
}
.controller-assignments__drawing {
  position: relative;
  width: 100%;
  max-width: 26rem;
  margin: var(--r-space-3) auto;
  color: var(--r-color-fg);
}
svg {
  display: block;
  width: 100%;
  height: 100%;
}
.controller-assignments__marks {
  fill: currentColor;
  text-anchor: middle;
  font-family: sans-serif;
  font-size: 1.8px;
}
.controller-assignments__selection {
  fill: color-mix(in srgb, var(--r-color-brand-primary) 25%, transparent);
  stroke: var(--r-color-brand-primary);
  stroke-width: 0.7;
}
.controller-assignments__hit {
  position: absolute;
  transform: translate(-50%, -50%);
  width: 1.5rem;
  height: 1.5rem;
  min-width: 0;
  padding: 0;
  border-radius: var(--r-radius-full);
  opacity: 0;
}
.controller-assignments__hit:focus-visible {
  opacity: 1;
  outline: 2px solid var(--r-color-brand-primary);
}
.controller-assignments__current {
  display: flex;
  gap: var(--r-space-2);
  flex-wrap: wrap;
  align-items: baseline;
  min-height: 2rem;
}
.controller-assignments__current > span:last-child {
  color: var(--r-color-brand-primary);
}
.controller-assignments__note {
  margin: 0 0 var(--r-space-2);
}
.controller-assignments__legend {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--r-space-1);
}
.controller-assignments__entry,
.controller-assignments__passive {
  display: flex;
  justify-content: flex-start;
  gap: var(--r-space-2);
  height: auto;
  min-height: 2.75rem;
  white-space: normal;
  font-size: var(--r-font-size-md);
  text-align: start;
}
.controller-assignments__entry :deep(.r-btn__content) {
  display: flex;
  justify-content: flex-start;
  gap: var(--r-space-2);
  flex-wrap: wrap;
}
.controller-assignments__passive {
  padding: var(--r-space-2);
  flex-wrap: wrap;
  color: var(--r-color-fg-muted);
}
.controller-assignments__legend strong {
  font-weight: 600;
  overflow-wrap: anywhere;
}
</style>
