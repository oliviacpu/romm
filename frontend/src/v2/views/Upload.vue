<script setup lang="ts">
// Upload: Library Tools view that posts ROM files to a chosen
// platform. Replaces the old emitter-driven `UploadRomDialog`; entry
// points (UserMenu, Platform.vue kebab) now navigate here with the
// `?platform=<id>` query param when they have a preselection.
//
// Flow mirrors the dialog version that came before it:
//   1. On mount, fetch the supported-platforms catalogue (v1's
//      sentinel id=-1 "the fs_slug exists but no Platform record yet"
//      is preserved, uploading auto-creates the platform via
//      `platformApi.uploadPlatform({ fsSlug })`).
//   2. User picks a platform (PlatformSelect handles search +
//      iconography) and adds files via drop zone or native picker.
//   3. Upload streams through `romApi.uploadRoms` (already wired to
//      `storeUpload`, the v2 UploadProgressToast shows the bar). On
//      success we stay on the view (this is a tool, users will often
//      upload more) but clear the file list. A scan is kicked off
//      automatically, unless one is already running, so newly arrived
//      files get matched.
import { RBtn, RChip, RDropzone, RIcon, RTextField } from "@v2/lib";
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute } from "vue-router";
import platformApi from "@/services/api/platform";
import romApi from "@/services/api/rom";
import type {
  PlatformUploadPolicy,
  RomInspectionLimits,
  RomInspectionResult,
} from "@/services/api/rom";
import storeHeartbeat from "@/stores/heartbeat";
import type { Platform } from "@/stores/platforms";
import storeScanning from "@/stores/scanning";
import storeUpload from "@/stores/upload";
import { formatBytes } from "@/utils";
import {
  gameFolderPlan,
  suggestedGameName,
  type GameFolderError,
} from "@/utils/gameFolderUpload";
import { inspectionConflict } from "@/utils/romIdentification";
import { settleWithLimit } from "@/utils/settleWithLimit";
import { uploadPath } from "@/utils/uploadFiles";
import {
  folderIssue,
  singleFileIssue,
  type UploadIssue,
} from "@/utils/uploadPolicy";
import PlatformSelect from "@/v2/components/shared/PlatformSelect.vue";
import { useScanTrigger } from "@/v2/composables/useScanTrigger";
import { useSnackbar } from "@/v2/composables/useSnackbar";

const { t } = useI18n();
const route = useRoute();
const snackbar = useSnackbar();
const heartbeatStore = storeHeartbeat();
const uploadStore = storeUpload();
const scanningStore = storeScanning();
const { startScan } = useScanTrigger();

const files = ref<File[]>([]);
const supportedPlatforms = ref<Platform[]>([]);
const platformsLoading = ref(false);
const selectedPlatformSlug = ref<string | null>(null);
const uploading = ref(false);
const multiDisc = ref(false);
const gameName = ref("");
const uploadPolicies = ref<Record<string, PlatformUploadPolicy>>({});
const validationIssue = ref<UploadIssue | null>(null);
const scanningUploaded = ref(0);
const inspectionLimits = ref<RomInspectionLimits | null>(null);
type Inspection =
  | { status: "checking" }
  | { status: "error" }
  | { status: "ready"; result: RomInspectionResult };
const inspections = ref(new Map<string, Inspection>());
const filePlatforms = ref(new Map<string, string | null>());
const defaultConfirmed = ref(false);

const uploadDz = ref<InstanceType<typeof RDropzone> | null>(null);

// ── Platform list bootstrap ────────────────────────────────────
async function loadPlatforms() {
  platformsLoading.value = true;
  try {
    const [{ data }, policies, limits] = await Promise.all([
      platformApi.getSupportedPlatforms(),
      romApi.getUploadPolicies(),
      romApi.getInspectionLimits(),
    ]);
    uploadPolicies.value = policies;
    inspectionLimits.value = limits;
    void inspectFiles(files.value);
    supportedPlatforms.value = data
      .slice()
      .sort((a, b) => a.name.localeCompare(b.name));
    applyPreselectFromQuery();
  } catch (err) {
    const e = err as {
      response?: { data?: { detail?: string } };
      message?: string;
    };
    snackbar.error(
      t("common.unable-to-load-platforms", {
        error:
          e?.response?.data?.detail || e?.message || t("common.unknown-error"),
      }),
      { icon: "mdi-close-circle" },
    );
  } finally {
    platformsLoading.value = false;
  }
}

// Honour `?platform=<id>` on first paint and whenever the query
// changes (in-app navigation between Platforms keeps the view but
// swaps preselection). Falls back to `null` so the picker reads as
// empty when no query is present.
function applyPreselectFromQuery() {
  defaultConfirmed.value = false;
  const raw = route.query.platform;
  const value = Array.isArray(raw) ? raw[0] : raw;
  if (!value) {
    selectedPlatformSlug.value = null;
    return;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    selectedPlatformSlug.value = null;
    return;
  }
  selectedPlatformSlug.value =
    supportedPlatforms.value.find((p) => p.id === parsed)?.slug ?? null;
}

onMounted(() => {
  void loadPlatforms();
});

watch(() => route.query.platform, applyPreselectFromQuery);
watch([selectedPlatformSlug, multiDisc, gameName], () => {
  validationIssue.value = null;
});
watch(
  () => scanningStore.scanning,
  (scanning) => {
    if (!scanning) scanningUploaded.value = 0;
  },
);

const selectedPlatform = computed<Platform | null>(() => {
  if (selectedPlatformSlug.value === null) return null;
  return (
    supportedPlatforms.value.find(
      (p) => p.slug === selectedPlatformSlug.value,
    ) ?? null
  );
});
const selectedPolicy = computed(() =>
  selectedPlatform.value
    ? uploadPolicies.value[selectedPlatform.value.fs_slug]
    : undefined,
);

const folderMode = computed(() =>
  files.value.some((file) => uploadPath(file).includes("/")),
);
const folderPlan = computed(() =>
  folderMode.value
    ? gameFolderPlan(files.value, gameName.value, multiDisc.value)
    : null,
);
function destinationFor(file: File): Platform | null {
  const path = uploadPath(file);
  const inspection = inspections.value.get(path);
  const detected =
    inspection?.status === "ready" && inspection.result.platforms.length === 1
      ? inspection.result.platforms[0]
      : null;
  const slug = filePlatforms.value.has(path)
    ? filePlatforms.value.get(path)
    : (detected ??
      (defaultConfirmed.value ? selectedPlatformSlug.value : null));
  return (
    supportedPlatforms.value.find((platform) => platform.slug === slug) ?? null
  );
}

function fileBlocked(file: File): boolean {
  const inspection = inspections.value.get(uploadPath(file));
  const target = folderMode.value
    ? selectedPlatform.value
    : destinationFor(file);
  return (
    inspection?.status !== "ready" ||
    !target ||
    inspectionConflict(inspection.result, target.slug)
  );
}

function inspectionLabel(file: File): string {
  const inspection = inspections.value.get(uploadPath(file));
  if (!inspection || inspection.status === "checking")
    return t("common.upload-detecting");
  if (inspection.status === "error")
    return t("common.upload-inspection-failed");
  if (inspection.result.invalid) return t("common.upload-invalid-file");
  if (inspection.result.platforms.length > 1)
    return t("common.upload-mixed-archive");
  const detected = supportedPlatforms.value.find(
    (platform) => platform.slug === inspection.result.platforms[0],
  );
  const target = folderMode.value
    ? selectedPlatform.value
    : destinationFor(file);
  if (target && inspectionConflict(inspection.result, target.slug))
    return t("common.upload-platform-conflict");
  return detected
    ? t("common.upload-platform-detected", { platform: detected.name })
    : t("common.upload-platform-unidentified");
}

function inspectionSource(file: File): string | null {
  const inspection = inspections.value.get(uploadPath(file));
  if (inspection?.status !== "ready" || !inspection.result.platforms.length)
    return null;
  const source: Record<string, string> = {
    header: "common.upload-source-header",
    "archive-headers": "common.upload-source-archive",
    "library-hash": "common.upload-source-library",
  };
  const key = source[inspection.result.evidence];
  return key ? t(key) : null;
}

async function inspectFiles(picked: File[]) {
  const limits = inspectionLimits.value;
  if (!limits) return;
  for (const file of picked)
    inspections.value.set(uploadPath(file), { status: "checking" });
  await settleWithLimit(picked, 2, async (file) => {
    try {
      const result = await romApi.inspectRomUpload(file, limits);
      if (files.value.includes(file))
        inspections.value.set(uploadPath(file), { status: "ready", result });
    } catch {
      if (files.value.includes(file))
        inspections.value.set(uploadPath(file), { status: "error" });
    }
  });
}

const formatIssue = computed(() => {
  if (folderMode.value) return null;
  for (const file of files.value) {
    const target = destinationFor(file);
    const issue = singleFileIssue(
      [file],
      target ? uploadPolicies.value[target.fs_slug] : undefined,
    );
    if (issue) return issue;
  }
  return null;
});
const currentIssue = computed(() => validationIssue.value ?? formatIssue.value);
const supportedFormats = computed(
  () => selectedPolicy.value?.launch.join(", ") ?? "",
);

const canUpload = computed(
  () =>
    files.value.length > 0 &&
    !uploading.value &&
    !currentIssue.value &&
    files.value.every((file) => !fileBlocked(file)) &&
    (!folderMode.value || (!!selectedPlatform.value && !!folderPlan.value?.ok)),
);

function issueMessage(issue: UploadIssue): string {
  if (issue.kind === "unsupported") {
    const file = files.value.find((entry) => entry.name === issue.file);
    const target = file ? destinationFor(file) : null;
    return t("common.upload-format-rejected", {
      file: issue.file,
      formats:
        (target
          ? uploadPolicies.value[target.fs_slug]?.launch.join(", ")
          : null) ?? supportedFormats.value,
    });
  }
  if (issue.kind === "needs-folder") {
    return t("common.upload-folder-required", { file: issue.file });
  }
  return t("common.upload-folder-invalid", {
    file: "file" in issue ? issue.file : issue.disc || gameName.value,
  });
}
const folderErrorKeys: Record<GameFolderError, string> = {
  "one-folder": "common.folder-one-game",
  "disc-folders": "common.folder-disc-folders",
  "disc-order": "common.folder-disc-order",
  "game-name": "common.folder-game-name",
  "duplicate-path": "common.folder-duplicate-path",
};

function displayPath(file: File): string {
  const plan = folderPlan.value;
  return plan?.ok ? `${plan.name}/${plan.paths.get(file)}` : uploadPath(file);
}

// ── File handling ───────────────────────────────────────────────
function addFiles(picked: File[]) {
  if (!picked.length) return;
  if (uploading.value) return;
  validationIssue.value = null;
  const seen = new Set(files.value.map(uploadPath));
  const fresh = picked.filter((f) => {
    const path = uploadPath(f);
    if (
      f.name === ".DS_Store" ||
      f.name.startsWith("._") ||
      f.name === "Thumbs.db"
    ) {
      return false;
    }
    if (seen.has(path)) return false;
    seen.add(path);
    return true;
  });
  if (fresh.length > 0) {
    if (files.value.length === 0 && uploadPath(fresh[0]!).includes("/")) {
      gameName.value = suggestedGameName(uploadPath(fresh[0]!));
    }
    files.value = [...files.value, ...fresh];
    void inspectFiles(fresh);
  }
}

function removeFile(name: string) {
  validationIssue.value = null;
  inspections.value.delete(name);
  filePlatforms.value.delete(name);
  files.value = files.value.filter((f) => uploadPath(f) !== name);
  if (files.value.length === 0) gameName.value = "";
}

function chooseFilePlatform(file: File, slug: string | null) {
  filePlatforms.value.set(uploadPath(file), slug);
  validationIssue.value = null;
}

function fileReadError(error: Error) {
  snackbar.error(t("common.unable-to-upload-roms", { error: error.message }));
}

// ── Upload ──────────────────────────────────────────────────────
async function upload() {
  if (!canUpload.value) return;
  const platform = folderMode.value
    ? selectedPlatform.value
    : destinationFor(files.value[0]!);
  if (!platform) return;
  const plan = folderPlan.value;
  if (folderMode.value && (!plan || !plan.ok)) return;
  if (formatIssue.value) return;
  uploading.value = true;
  const batch = [...files.value];

  const destinations = new Map(
    batch.map((file) => [
      uploadPath(file),
      folderMode.value ? platform : destinationFor(file)!,
    ]),
  );
  const targets = new Map(
    [...destinations.values()].map((target) => [target.slug, target]),
  );
  const platformIds = new Map<string, number>();

  try {
    const issue = plan?.ok
      ? await folderIssue(plan.paths, selectedPolicy.value)
      : formatIssue.value;
    if (issue) {
      validationIssue.value = issue;
      return;
    }
    validationIssue.value = null;
    for (const target of targets.values()) {
      let id = target.id;
      if (id === -1) {
        const { data: created } = await platformApi.uploadPlatform({
          fsSlug: target.fs_slug,
        });
        id = created.id;
        supportedPlatforms.value = supportedPlatforms.value.map((entry) =>
          entry.slug === target.slug ? { ...entry, id } : entry,
        );
        snackbar.success(t("common.platform-created", { name: target.name }), {
          icon: "mdi-check-bold",
        });
      }
      platformIds.set(target.slug, id);
    }
    const platformForFile = (file: File) =>
      platformIds.get(destinations.get(uploadPath(file))!.slug)!;
    const platformId = platformForFile(batch[0]!);

    const responses = plan?.ok
      ? await romApi
          .uploadGameFolder({ platformId, name: plan.name, paths: plan.paths })
          .then(() => batch.map(() => ({ status: "fulfilled" as const })))
      : await romApi.uploadRoms({
          platformId,
          filesToUpload: batch,
          ...(targets.size > 1 ? { platformForFile } : {}),
        });

    const ok = responses.filter((r) => r.status === "fulfilled").length;
    const fail = responses.filter((r) => r.status === "rejected").length;

    if (ok === 0) {
      snackbar.warning(t("common.all-files-skipped"), {
        icon: "mdi-information-outline",
      });
    } else {
      if (fail === 0) uploadStore.reset();
      snackbar.success(
        fail === 0
          ? t("common.uploaded-and-scanning", { ok })
          : t("common.uploaded-with-failed", { ok, fail }),
        { icon: "mdi-check-bold" },
      );

      // Give the backend a beat to finish writing before we ask it to
      // scan, v1 uses a 2s buffer for the same reason.
      const uploadedPlatforms = [
        ...new Set(
          batch
            .filter((_, index) => responses[index]?.status === "fulfilled")
            .map(platformForFile),
        ),
      ];
      setTimeout(() => {
        const started = startScan([
          {
            platforms: uploadedPlatforms,
            type: "quick",
            apis: heartbeatStore
              .getEnabledMetadataOptions()
              .map((s) => s.value),
          },
        ]);
        if (started) scanningUploaded.value = ok;
      }, 2000);

      // Clear the list so the next batch starts fresh; keep the
      // platform selected so a user can chain uploads.
      for (const [index, file] of batch.entries()) {
        if (responses[index]?.status === "fulfilled") {
          inspections.value.delete(uploadPath(file));
          filePlatforms.value.delete(uploadPath(file));
        }
      }
      files.value = batch.filter(
        (_, index) => responses[index]?.status === "rejected",
      );
      if (files.value.length === 0) {
        gameName.value = "";
        multiDisc.value = false;
      }
    }
  } catch (err) {
    const e = err as {
      response?: { data?: { detail?: string }; statusText?: string };
      message?: string;
    };
    snackbar.error(
      t("common.unable-to-upload-roms", {
        error:
          e?.response?.data?.detail ||
          e?.response?.statusText ||
          e?.message ||
          t("common.unknown-error"),
      }),
      { icon: "mdi-close-circle" },
    );
  } finally {
    uploading.value = false;
  }
}
</script>

<template>
  <div class="r-v2-upload r-v2-section-stack">
    <p v-if="scanningUploaded" role="status">
      {{ t("common.uploaded-and-scanning", { ok: scanningUploaded }) }}
    </p>
    <div class="r-v2-upload__top">
      <PlatformSelect
        v-model="selectedPlatformSlug"
        class="r-v2-upload__platform"
        :items="supportedPlatforms"
        item-key="slug"
        promote-filled
        :placeholder="t('common.select-platform')"
        density="comfortable"
        prefix-label="stacked"
        :icon-size="22"
        :search-placeholder="t('common.search')"
        :disabled="platformsLoading || uploading"
        @update:model-value="defaultConfirmed = true"
      >
        <template #prefix-label>
          <RIcon icon="mdi-controller" size="14" />
          {{
            t(folderMode ? "common.platform" : "common.upload-default-platform")
          }}
        </template>
      </PlatformSelect>
      <RBtn
        variant="outlined"
        :aria-pressed="multiDisc"
        :disabled="uploading"
        @click="multiDisc = !multiDisc"
      >
        {{ t("common.multi-disc-game") }}
      </RBtn>
      <RBtn
        variant="outlined"
        prepend-icon="mdi-folder-plus-outline"
        :disabled="uploading"
        @click="uploadDz?.openDirectory()"
      >
        {{ t("common.add-folder") }}
      </RBtn>
      <RBtn
        variant="flat"
        color="primary"
        prepend-icon="mdi-cloud-upload-outline"
        data-testid="upload-submit"
        :disabled="!canUpload"
        :loading="uploading"
        @click="upload"
      >
        {{ t("common.upload") }}
      </RBtn>
    </div>

    <div v-if="folderMode || multiDisc" class="r-v2-upload__folder-options">
      <RTextField
        v-model="gameName"
        :label="t('common.folder-game-name-label')"
      />
      <p>
        {{
          t(multiDisc ? "common.multi-disc-hint" : "common.game-folder-hint")
        }}
      </p>
      <p v-if="folderPlan && !folderPlan.ok" role="alert">
        {{ t(folderErrorKeys[folderPlan.error]) }}
      </p>
    </div>
    <p class="r-v2-upload__guidance">{{ t("common.upload-detection-hint") }}</p>
    <p v-if="selectedPolicy" class="r-v2-upload__guidance">
      {{ t("common.upload-supported-formats", { formats: supportedFormats }) }}
    </p>
    <p v-if="currentIssue" class="r-v2-upload__error" role="alert">
      {{ issueMessage(currentIssue) }}
    </p>

    <!-- Drop zone, CTA when empty, file list (with drag overlay) when
           populated. -->
    <RDropzone
      v-if="files.length === 0"
      ref="uploadDz"
      fill
      :title="t('common.dropzone-title')"
      :hint="t('common.dropzone-description')"
      :active-title="t('common.dropzone-drag-over')"
      :input-label="t('common.upload-roms')"
      :directory-input-label="t('common.add-folder')"
      :disabled="uploading"
      multiple
      @files="addFiles"
      @error="fileReadError"
    />
    <RDropzone
      v-else
      ref="uploadDz"
      fill
      overlay
      :release-label="t('common.dropzone-drag-over')"
      :input-label="t('common.upload-roms')"
      :directory-input-label="t('common.add-folder')"
      :disabled="uploading"
      multiple
      @files="addFiles"
      @error="fileReadError"
    >
      <div class="r-v2-upload__filled">
        <ul class="r-v2-upload__list">
          <li v-for="f in files" :key="uploadPath(f)" class="r-v2-upload__row">
            <RIcon icon="mdi-file-outline" size="14" />
            <span class="r-v2-upload__row-name" :title="displayPath(f)">{{
              displayPath(f)
            }}</span>
            <RChip size="x-small" variant="translucent">
              {{ formatBytes(f.size) }}
            </RChip>
            <div class="r-v2-upload__destination">
              <span
                :class="{ 'r-v2-upload__error': fileBlocked(f) }"
                role="status"
                >{{ inspectionLabel(f) }}</span
              >
              <span v-if="inspectionSource(f)" class="r-v2-upload__guidance">{{
                inspectionSource(f)
              }}</span>
              <PlatformSelect
                v-if="!folderMode"
                :model-value="destinationFor(f)?.slug ?? null"
                :items="supportedPlatforms"
                item-key="slug"
                :placeholder="t('common.select-platform')"
                :aria-label="`${t('common.platform')}: ${f.name}`"
                :disabled="uploading"
                @update:model-value="chooseFilePlatform(f, $event)"
              />
              <RBtn
                v-if="inspections.get(uploadPath(f))?.status === 'error'"
                variant="text"
                :disabled="uploading"
                @click="inspectFiles([f])"
                >{{ t("common.try-again") }}</RBtn
              >
            </div>
            <RBtn
              variant="text"
              size="x-small"
              icon="mdi-close"
              color="danger"
              :aria-label="t('common.remove')"
              :disabled="uploading"
              @click="removeFile(uploadPath(f))"
            />
          </li>
        </ul>
        <footer class="r-v2-upload__filled-foot">
          <span>
            {{ t("common.upload-files-selected", { count: files.length }) }}
          </span>
          <RBtn
            variant="flat"
            color="primary"
            prepend-icon="mdi-plus"
            :disabled="uploading"
            @click="uploadDz?.open()"
          >
            {{ t("common.add") }}
          </RBtn>
        </footer>
      </div>
    </RDropzone>
  </div>
</template>

<style scoped>
/* Desktop runs in SettingsLayout `fill` mode, so the dropzone grows to the
   viewport bottom. Phones keep the document scroll and the capped list. */
.r-v2-upload {
  flex: 1 1 auto;
  min-height: 0;
}
.r-v2-upload__top {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}
.r-v2-upload__platform {
  flex: 1 1 auto;
  min-width: min(100%, 240px);
}
.r-v2-upload__destination {
  grid-column: 2 / 4;
  grid-row: 2;
  display: grid;
  gap: 6px;
  min-width: min(100%, 230px);
}
.r-v2-upload__guidance,
.r-v2-upload__error {
  margin: 0;
  font-size: 13px;
}
.r-v2-upload__guidance {
  color: var(--r-color-fg-muted);
}
.r-v2-upload__error {
  color: var(--r-color-danger);
}
.r-v2-upload__folder-options {
  display: grid;
  gap: 6px;
  max-width: 560px;
}
.r-v2-upload__folder-options p {
  margin: 0;
  color: var(--r-color-fg-muted);
  font-size: 13px;
}

/* ── Filled state ────────────────────────────────────────────── */
.r-v2-upload__filled {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.r-v2-upload__filled-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: var(--r-font-weight-semibold);
  color: var(--r-color-fg);
}

.r-v2-upload__list {
  list-style: none;
  margin: 0;
  padding: 0;
  border: 1px solid var(--r-color-border);
  border-radius: var(--r-radius-md);
  background: var(--r-color-bg-elevated);
  flex: 1 1 auto;
  overflow-y: auto;
}
html[data-bp~="sm-and-down"] .r-v2-upload__list {
  max-height: 320px;
}
.r-v2-upload__row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto auto;
  gap: 10px;
  align-items: center;
  padding: 8px 12px;
  font-size: 13px;
  color: var(--r-color-fg);
  border-bottom: 1px solid var(--r-color-border);
}
.r-v2-upload__row > :last-child {
  grid-column: 4;
  grid-row: 1;
}
.r-v2-upload__row:last-child {
  border-bottom: 0;
}
.r-v2-upload__row-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
