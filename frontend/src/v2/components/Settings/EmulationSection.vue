<script setup lang="ts">
import { RAlert, RBtn, RForm, RSelect, RSpinner } from "@v2/lib";
import { useIntervalFn } from "@vueuse/core";
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import type {
  EmulationProfile,
  EmulationProfileResponse,
  EmulationStatus,
} from "@/__generated__";
import emulationApi from "@/services/api/emulation";
import { formatTimestamp } from "@/utils";
import ControllerAssignments from "@/v2/components/Settings/ControllerAssignments.vue";
import SettingsSection from "@/v2/components/Settings/SettingsSection.vue";
import { useFetchState } from "@/v2/composables/useFetchState";
import { useIsAlive } from "@/v2/composables/useIsAlive";
import { useRouteQueryParam } from "@/v2/composables/useRouteQueryParam";
import { useSnackbar } from "@/v2/composables/useSnackbar";

const { t, locale } = useI18n();
const snackbar = useSnackbar();
const alive = useIsAlive();
const system = useRouteQueryParam("sunshinePlatform", "ps2");
const gameSelection = useRouteQueryParam("sunshineGame");
const gameId = computed<string | null>({
  get: () => gameSelection.value || null,
  set: (value) => {
    gameSelection.value = value ?? "";
  },
});
const saving = ref(false);
const selectedConsoleButton = ref("a");
const draft = ref<EmulationProfile>({ bindings: {} });
const status = useFetchState(
  () => emulationApi.status().then(({ data }) => data),
  {
    enabled: false,
    platforms: [],
    games: [],
    sessions: [],
    buttons: {},
  } as EmulationStatus,
);
const profile = useFetchState(
  (platform: string, game: string | null) =>
    emulationApi.profile(platform, game).then(({ data }) => data),
  null as EmulationProfileResponse | null,
  { immediate: false },
);
const platform = computed(() =>
  status.state.value.platforms?.find((item) => item.id === system.value),
);
const games = computed(() => [
  { id: null, title: t("emulation.platform-default") },
  ...(status.state.value.games ?? []).filter(
    (game) => game.system === system.value,
  ),
]);
const buttons = computed(() =>
  Object.entries(status.state.value.buttons ?? {}).map(([id, label]) => ({
    id,
    label,
  })),
);
const bindings = computed(() => Object.entries(platform.value?.buttons ?? {}));
const xboxDiagramLabels = computed(() => ({
  ...status.state.value.buttons,
  ...Object.fromEntries(
    Object.entries(status.state.value.action_buttons ?? {}).filter(([key]) =>
      ["share", "guide"].includes(key),
    ),
  ),
}));
const xboxAssignments = computed(() => {
  const assigned = Object.fromEntries(
    bindings.value.map(([key, label]) => [binding(key), label]),
  );
  return Object.fromEntries(
    Object.keys(xboxDiagramLabels.value).map((key) => [
      key,
      [
        assigned[key],
        ...["menu", "quit"]
          .filter((action) => {
            const field = `${action}_shortcut` as
              "menu_shortcut" | "quit_shortcut";
            const id =
              draft.value[field] ?? profile.state.value?.inherited[field];
            return (status.state.value.shortcuts?.[id ?? ""] ?? []).includes(
              key,
            );
          })
          .map((action) => t(`emulation.${action}-shortcut`)),
      ]
        .filter(Boolean)
        .join(" / "),
    ]),
  );
});
const consoleAssignments = computed(() => {
  const names: Record<string, string> = {
    view: "View",
    menu: "Menu",
    l3: "L3",
    r3: "R3",
    up: "↑",
    down: "↓",
    left: "←",
    right: "→",
  };
  return Object.fromEntries(
    bindings.value.map(([key]) => {
      const button = binding(key);
      return [key, names[button] ?? button.toUpperCase()];
    }),
  );
});
const resolutions = computed(() =>
  (platform.value?.resolutions ?? []).map((id) => ({
    id,
    label: id === "native" ? t("emulation.native") : id,
  })),
);
const busy = computed(() => profile.isLoading.value || saving.value);
const shortcutsConflict = computed(
  () =>
    (draft.value.menu_shortcut ??
      profile.state.value?.inherited.menu_shortcut) ===
    (draft.value.quit_shortcut ?? profile.state.value?.inherited.quit_shortcut),
);
const sessions = computed(() =>
  [...(status.state.value.sessions ?? [])].reverse(),
);
const stale = computed(
  () =>
    !!status.state.value.updated &&
    Date.now() / 1000 - status.state.value.updated > 90,
);

watch(system, () => {
  gameId.value = null;
  selectedConsoleButton.value = "a";
});
watch(
  [system, gameId, () => status.state.value.enabled],
  ([platform, game, enabled]) => {
    if (enabled) void profile.execute(platform, game);
  },
  { immediate: true },
);
watch(profile.state, (value) => {
  if (value)
    draft.value = { ...value.saved, bindings: { ...value.saved.bindings } };
});

async function refresh(): Promise<void> {
  const listing = await status.execute();
  if (listing?.enabled && alive.value)
    await profile.execute(system.value, gameId.value);
}

useIntervalFn(() => {
  if (document.visibilityState === "visible" && status.state.value.enabled)
    void status.execute();
}, 10000);

function buttonChoices(key: string) {
  const trigger = ["lt", "rt"].includes(key);
  return buttons.value.filter(
    (button) => ["lt", "rt"].includes(button.id) === trigger,
  );
}

function assignDiagramButton(key: string): void {
  if (busy.value || !platform.value?.mapping) return;
  if (
    buttonChoices(selectedConsoleButton.value).some(
      (button) => button.id === key,
    )
  )
    setBinding(selectedConsoleButton.value, key);
}

function shortcutLabel(id: string | undefined | null): string {
  const chord = status.state.value.shortcuts?.[id ?? ""] ?? [];
  return chord.length
    ? chord
        .map((button) =>
          ["share", "guide", "view", "menu", "l3", "r3"].includes(button)
            ? t(`emulation.button-${button}`)
            : (status.state.value.action_buttons?.[button] ?? button),
        )
        .join(" + ")
    : t("emulation.no-shortcut");
}

function shortcutChoices(action: "menu" | "quit") {
  const inherited = profile.state.value?.inherited[`${action}_shortcut`];
  return [
    {
      id: null,
      label: `${shortcutLabel(inherited)} · ${t("emulation.inherit")}`,
    },
    ...Object.keys(status.state.value.shortcuts ?? {})
      .filter((id) => action !== "quit" || id !== "none")
      .map((id) => ({ id, label: shortcutLabel(id) })),
  ];
}

function inheritedLabel(field: "resolution" | "aspect" | "osd_scale"): string {
  const value = profile.state.value?.inherited[field];
  const label =
    value === "native"
      ? t("emulation.native")
      : value === "auto"
        ? t("emulation.auto")
        : value === "original"
          ? t(
              system.value === "gc"
                ? "emulation.game-aspect"
                : "emulation.original",
            )
          : field === "osd_scale"
            ? `${value}%`
            : String(value);
  return `${label} · ${t("emulation.inherit")}`;
}

function binding(key: string): string {
  return (
    draft.value.bindings?.[key] ??
    profile.state.value?.inherited.bindings?.[key] ??
    key
  );
}

function setBinding(key: string, value: string | null): void {
  const inherited = profile.state.value?.inherited.bindings ?? {};
  const values = { ...inherited, ...draft.value.bindings };
  const previous = values[key];
  const next = value ?? inherited[key];
  if (!next || !previous) return;
  const other = Object.keys(values).find(
    (target) => target !== key && values[target] === next,
  );
  if (other) values[other] = previous;
  values[key] = next;
  draft.value.bindings = Object.fromEntries(
    Object.entries(values).filter(
      ([target, source]) => source !== inherited[target],
    ),
  );
}

function inherit(): void {
  draft.value = { bindings: {} };
}

async function save(): Promise<void> {
  const current = profile.state.value;
  if (!current || busy.value || shortcutsConflict.value) return;
  const target = system.value;
  const game = gameId.value;
  const payload = {
    revision: current.revision,
    profile: { ...draft.value, bindings: { ...draft.value.bindings } },
  };
  saving.value = true;
  try {
    await emulationApi.save(target, game, payload);
    if (!alive.value) return;
    snackbar.success(t("emulation.saved"));
    await profile.execute(target, game);
  } catch {
    if (alive.value) snackbar.error(t("emulation.save-failed"));
  } finally {
    if (alive.value) saving.value = false;
  }
}

function timestamp(value: number): string {
  return formatTimestamp(new Date(value * 1000).toISOString(), locale.value);
}
</script>

<template>
  <SettingsSection :title="t('emulation.title')" icon="mdi-controller">
    <template #header-actions>
      <RBtn
        icon="mdi-refresh"
        variant="text"
        :tooltip="t('emulation.refresh')"
        :aria-label="t('emulation.refresh')"
        :loading="status.isLoading.value"
        @click="refresh"
      />
    </template>
    <div class="emulation-content">
      <RAlert v-if="status.error.value" type="error">{{
        t("emulation.unavailable")
      }}</RAlert>
      <RSpinner
        v-else-if="status.isLoading.value && !status.state.value.enabled"
      />
      <p v-else-if="!status.state.value.enabled">
        {{ t("emulation.not-configured") }}
      </p>
      <template v-else>
        <RAlert v-if="stale" type="warning">{{ t("emulation.stale") }}</RAlert>
        <p>{{ t("emulation.launch-help") }}</p>
        <div class="emulation-grid">
          <RSelect
            v-model="system"
            prefix-label="stacked"
            searchable
            :items="status.state.value.platforms ?? []"
            item-title="label"
            item-value="id"
            :label="t('emulation.platform')"
            :disabled="busy"
          />
          <RSelect
            v-model="gameId"
            prefix-label="stacked"
            searchable
            :items="games"
            item-title="title"
            item-value="id"
            :label="t('emulation.scope')"
            :disabled="busy"
          />
        </div>
        <RAlert v-if="profile.error.value" type="error">{{
          t("emulation.unavailable")
        }}</RAlert>
        <RSpinner v-else-if="profile.isLoading.value" />
        <RForm
          v-else-if="profile.state.value"
          disable-enter-submit
          @submit="save"
        >
          <div class="emulation-grid">
            <RSelect
              v-model="draft.resolution"
              prefix-label="stacked"
              :items="[
                { id: null, label: inheritedLabel('resolution') },
                ...resolutions,
              ]"
              item-title="label"
              item-value="id"
              :label="t('emulation.resolution')"
              :hint="t('emulation.resolution-help')"
              :disabled="saving || resolutions.length < 2"
            />
            <RSelect
              v-model="draft.aspect"
              prefix-label="stacked"
              :items="[
                { id: null, label: inheritedLabel('aspect') },
                {
                  id: 'original',
                  label: t(
                    system === 'gc'
                      ? 'emulation.game-aspect'
                      : 'emulation.original',
                  ),
                },
                ...(system === 'ps2'
                  ? [{ id: 'auto', label: t('emulation.auto') }]
                  : []),
                { id: '16:9', label: '16:9' },
              ]"
              item-title="label"
              item-value="id"
              :label="t('emulation.aspect')"
              :hint="t('emulation.widescreen-help')"
              :disabled="saving || !platform?.widescreen"
            />
            <RSelect
              v-model="draft.osd_scale"
              prefix-label="stacked"
              :items="[
                { id: null, label: inheritedLabel('osd_scale') },
                ...[100, 150, 200, 250, 300].map((id) => ({
                  id,
                  label: `${id}%`,
                })),
              ]"
              item-title="label"
              item-value="id"
              :label="t('emulation.message-size')"
              :hint="t('emulation.message-size-help')"
              :disabled="saving || ['gc', 'dreamcast', 'xbox'].includes(system)"
            />
          </div>
          <h3>{{ t("emulation.controller") }}</h3>
          <p>{{ t("emulation.controller-help") }}</p>
          <p>{{ t("emulation.diagram-help") }}</p>
          <div v-if="platform" class="emulation-diagrams">
            <ControllerAssignments
              :system="system"
              :title="platform.label"
              :labels="platform.buttons"
              :assignments="consoleAssignments"
              :selected="selectedConsoleButton"
              :selectable="Object.keys(platform.buttons)"
              :disabled="busy || !platform.mapping"
              @select="selectedConsoleButton = $event"
            />
            <ControllerAssignments
              system="xbox-series"
              title="Xbox Series X|S"
              :labels="xboxDiagramLabels"
              :assignments="xboxAssignments"
              :selected="binding(selectedConsoleButton)"
              :selectable="
                buttonChoices(selectedConsoleButton).map((button) => button.id)
              "
              :disabled="busy || !platform.mapping"
              @select="assignDiagramButton"
            />
          </div>
          <RAlert v-if="!platform?.mapping" type="info">{{
            t("emulation.mapping-unavailable")
          }}</RAlert>
          <div v-else class="emulation-grid">
            <RSelect
              v-for="[key, label] in bindings"
              :key="key"
              prefix-label="stacked"
              :model-value="binding(key)"
              :items="[
                { id: null, label: t('emulation.inherit') },
                ...buttonChoices(key),
              ]"
              item-title="label"
              item-value="id"
              :label="label"
              :disabled="saving"
              @update:model-value="setBinding(key, $event)"
            />
          </div>
          <h3>{{ t("emulation.shortcuts") }}</h3>
          <p>{{ t("emulation.shortcut-help") }}</p>
          <div class="emulation-grid">
            <RSelect
              v-model="draft.menu_shortcut"
              prefix-label="stacked"
              :items="shortcutChoices('menu')"
              item-title="label"
              item-value="id"
              :label="t('emulation.menu-shortcut')"
              :disabled="saving"
            />
            <RSelect
              v-model="draft.quit_shortcut"
              prefix-label="stacked"
              :items="shortcutChoices('quit')"
              item-title="label"
              item-value="id"
              :label="t('emulation.quit-shortcut')"
              :disabled="saving"
            />
          </div>
          <p>{{ t("emulation.share-help") }}</p>
          <RAlert v-if="shortcutsConflict" type="warning">{{
            t("emulation.shortcut-conflict")
          }}</RAlert>
          <div class="emulation-actions">
            <RBtn
              type="submit"
              :loading="saving"
              :disabled="stale || shortcutsConflict"
              >{{ t("emulation.save") }}</RBtn
            >
            <RBtn variant="text" :disabled="saving" @click="inherit">{{
              t("emulation.reset")
            }}</RBtn>
          </div>
        </RForm>
        <h3>{{ t("emulation.messages") }}</h3>
        <p>{{ t("emulation.messages-help") }}</p>
        <p v-if="!sessions.length">{{ t("emulation.no-sessions") }}</p>
        <article
          v-for="session in sessions"
          :key="session.id"
          class="emulation-session"
        >
          <h4>
            {{ session.game }} ·
            {{
              status.state.value.platforms?.find((p) => p.id === session.system)
                ?.label
            }}
          </h4>
          <p>{{ timestamp(session.started) }}</p>
          <p v-if="!session.messages.length">
            {{ t("emulation.no-messages") }}
          </p>
          <RAlert
            v-for="(message, index) in session.messages"
            :key="index"
            :type="message.level"
          >
            <strong>{{ message.source }}</strong>
            <pre>{{ message.text }}</pre>
          </RAlert>
        </article>
      </template>
    </div>
  </SettingsSection>
</template>

<style scoped>
.emulation-content {
  padding: var(--r-space-4);
}
.emulation-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 15rem), 1fr));
  gap: var(--r-space-4);
}
.emulation-diagrams {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 22rem), 1fr));
  gap: var(--r-space-4);
  margin-block: var(--r-space-4);
}
.emulation-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--r-space-3);
}
.emulation-session {
  padding-block: var(--r-space-4);
  border-top: 1px solid var(--r-color-border);
}
.emulation-session pre,
.emulation-session strong {
  color: var(--r-color-fg);
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font: inherit;
  margin: 0;
}
h3 {
  margin-block: var(--r-space-5) var(--r-space-3);
}
</style>
