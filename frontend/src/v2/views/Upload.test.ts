import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import { platformFixture } from "@/utils/platform.fixtures";
import Upload from "./Upload.vue";

const {
  getSupportedPlatforms,
  uploadPlatform,
  uploadRoms,
  getUploadPolicies,
  getInspectionLimits,
  inspectRomUpload,
  emit,
  warning,
  scanning,
} = vi.hoisted(() => ({
  getSupportedPlatforms: vi.fn(),
  uploadPlatform: vi.fn(),
  uploadRoms: vi.fn(),
  getUploadPolicies: vi.fn().mockResolvedValue({}),
  getInspectionLimits: vi
    .fn()
    .mockResolvedValue({ head_bytes: 131072, tail_bytes: 1048576 }),
  inspectRomUpload: vi.fn(),
  emit: vi.fn(),
  warning: vi.fn(),
  scanning: {
    scanning: false,
    startedInThisTab: false,
    setScanning(value: boolean) {
      this.scanning = value;
    },
  },
}));

vi.mock("vue-i18n");

vi.mock("vue-router", async (importOriginal) => ({
  ...(await importOriginal<typeof import("vue-router")>()),
  useRoute: () => ({ query: {} }),
}));

vi.mock("@/services/api/platform", () => ({
  default: {
    getSupportedPlatforms,
    uploadPlatform,
  },
}));

vi.mock("@/services/api/rom", () => ({
  default: {
    uploadRoms,
    getUploadPolicies,
    getInspectionLimits,
    inspectRomUpload,
  },
}));

vi.mock("@/services/socket", () => ({
  default: { connected: true, connect: vi.fn(), emit },
}));

vi.mock("@/stores/heartbeat", () => ({
  default: () => ({ getEnabledMetadataOptions: () => [] }),
}));

vi.mock("@/stores/scanning", () => ({
  default: () => scanning,
}));

vi.mock("@/stores/upload", () => ({
  default: () => ({ reset: vi.fn() }),
}));

vi.mock("@/v2/composables/useSnackbar", () => ({
  useSnackbar: () => ({
    error: vi.fn(),
    success: vi.fn(),
    warning,
  }),
}));

const stubs = {
  PlatformSelect: {
    props: ["modelValue", "items", "itemKey"],
    emits: ["update:modelValue"],
    template:
      '<button class="platform-select" :data-item-key="itemKey" @click="$emit(\'update:modelValue\', \'3do\')" />',
  },
  RDropzone: {
    emits: ["files"],
    template:
      "<div><button class=\"dropzone\" @click=\"$emit('files', [{ name: 'game.rom', size: 3 }])\" /><button class=\"dropzone-mixed\" @click=\"$emit('files', [{ name: 'good.rom', size: 3 }, { name: 'bad.rom', size: 3 }])\" /><slot /></div>",
  },
  RBtn: {
    props: ["disabled"],
    emits: ["click"],
    template:
      '<button class="upload" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
  },
  RChip: true,
  RIcon: true,
};

const threeDo = platformFixture({
  id: -1,
  slug: "3do",
  name: "3DO Interactive Multiplayer",
  missing_from_fs: true,
});

async function uploadOneFile() {
  const wrapper = mount(Upload, { global: { stubs } });
  await flushPromises();
  await wrapper.get(".platform-select").trigger("click");
  await wrapper.get(".dropzone").trigger("click");
  await nextTick();
  await flushPromises();
  await wrapper.get('[data-testid="upload-submit"]').trigger("click");
  await flushPromises();
  return wrapper;
}

const unknownInspection = {
  format: "unknown",
  platforms: [],
  evidence: "unknown",
  invalid: false,
  members: [],
  incompatible_platforms: [],
};
beforeEach(() => {
  inspectRomUpload.mockResolvedValue(unknownInspection);
});

describe("Upload platform selection", () => {
  it("uses the unique slug when unsupported platforms share sentinel id -1", async () => {
    const zx80 = platformFixture({
      id: -1,
      slug: "zx80",
      name: "ZX80",
      missing_from_fs: true,
    });
    getSupportedPlatforms.mockResolvedValueOnce({ data: [zx80, threeDo] });
    uploadPlatform.mockResolvedValueOnce({ data: { ...threeDo, id: 123 } });
    uploadRoms.mockResolvedValueOnce([{ status: "fulfilled" }]);

    const wrapper = await uploadOneFile();

    expect(wrapper.get(".platform-select").attributes("data-item-key")).toBe(
      "slug",
    );
    expect(uploadPlatform).toHaveBeenCalledWith({ fsSlug: "3do" });
    expect(uploadRoms).toHaveBeenCalledWith({
      platformId: 123,
      filesToUpload: [expect.objectContaining({ name: "game.rom" })],
    });
  });
});

describe("Upload follow-up scan", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["setTimeout"] });
    scanning.scanning = false;
    scanning.startedInThisTab = false;
    getSupportedPlatforms.mockResolvedValueOnce({
      data: [{ ...threeDo, id: 7, missing_from_fs: false }],
    });
    uploadRoms.mockResolvedValueOnce([{ status: "fulfilled" }]);
  });

  it("scans the platform once the upload lands", async () => {
    await uploadOneFile();
    vi.runAllTimers();

    expect(emit).toHaveBeenCalledOnce();
    expect(emit).toHaveBeenCalledWith("scan", {
      platforms: [7],
      type: "quick",
      apis: [],
    });
  });

  it("scans committed files when another upload fails", async () => {
    uploadRoms.mockReset();
    uploadRoms.mockResolvedValueOnce([
      { status: "fulfilled" },
      { status: "rejected" },
    ]);
    const wrapper = mount(Upload, { global: { stubs } });
    await flushPromises();
    await wrapper.get(".platform-select").trigger("click");
    await wrapper.get(".dropzone-mixed").trigger("click");
    await nextTick();
    await flushPromises();
    await wrapper.get('[data-testid="upload-submit"]').trigger("click");
    await flushPromises();
    vi.runAllTimers();

    expect(emit).toHaveBeenCalledWith("scan", {
      platforms: [7],
      type: "quick",
      apis: [],
    });
  });

  it("does not request a second scan while one is running", async () => {
    await uploadOneFile();
    scanning.scanning = true;
    vi.runAllTimers();

    expect(emit).not.toHaveBeenCalled();
    expect(warning).toHaveBeenCalledWith(
      "scan.scan-in-progress",
      expect.anything(),
    );
  });
});

const detected = (platform: string) => ({
  ...unknownInspection,
  format: "cartridge",
  platforms: [platform],
  evidence: "archive-headers",
});
const n64 = platformFixture({
  id: 64,
  slug: "n64",
  fs_slug: "custom-n64",
  name: "Nintendo 64",
});
const genesis = platformFixture({
  id: 16,
  slug: "genesis",
  fs_slug: "genesis",
  name: "Sega Genesis",
});

async function mixedFixture(files: File[]) {
  getSupportedPlatforms.mockResolvedValueOnce({ data: [n64, genesis] });
  const wrapper = mount(Upload, { global: { stubs } });
  await flushPromises();
  wrapper.findComponent(stubs.RDropzone).vm.$emit("files", files);
  await flushPromises();
  return wrapper;
}

describe("Content-based upload destinations", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["setTimeout"] });
    scanning.scanning = false;
  });

  it("uploads a mixed batch to separate detected platforms without a global selection", async () => {
    const first = new File(["n64"], "first.zip");
    const second = new File(["genesis"], "second.zip");
    inspectRomUpload
      .mockResolvedValueOnce(detected("n64"))
      .mockResolvedValueOnce(detected("genesis"));
    uploadRoms.mockResolvedValueOnce([
      { status: "fulfilled" },
      { status: "fulfilled" },
    ]);
    const wrapper = await mixedFixture([first, second]);
    expect(
      wrapper.get('[data-testid="upload-submit"]').attributes("disabled"),
    ).toBeUndefined();
    await wrapper.get('[data-testid="upload-submit"]').trigger("click");
    await flushPromises();
    const options = uploadRoms.mock.lastCall![0];
    expect(options.platformForFile(first)).toBe(64);
    expect(options.platformForFile(second)).toBe(16);
    vi.runAllTimers();
    expect(emit).toHaveBeenCalledWith("scan", {
      platforms: [64, 16],
      type: "quick",
      apis: [],
    });
    wrapper.unmount();
  });

  it("rejects a destination that conflicts with a detected cartridge header", async () => {
    inspectRomUpload.mockResolvedValueOnce(detected("genesis"));
    const wrapper = await mixedFixture([new File(["data"], "game.zip")]);
    wrapper
      .findAllComponents(stubs.PlatformSelect)[1]!
      .vm.$emit("update:modelValue", "n64");
    await nextTick();
    expect(wrapper.text()).toContain("common.upload-platform-conflict");
    expect(
      wrapper.get('[data-testid="upload-submit"]').attributes("disabled"),
    ).toBeDefined();
    wrapper.unmount();
  });

  it("requires a deliberate destination for an unidentified file", async () => {
    const wrapper = await mixedFixture([new File(["data"], "unknown.bin")]);
    expect(wrapper.text()).toContain("common.upload-platform-unidentified");
    expect(
      wrapper.get('[data-testid="upload-submit"]').attributes("disabled"),
    ).toBeDefined();
    wrapper
      .findAllComponents(stubs.PlatformSelect)[1]!
      .vm.$emit("update:modelValue", "n64");
    await nextTick();
    expect(
      wrapper.get('[data-testid="upload-submit"]').attributes("disabled"),
    ).toBeUndefined();
    wrapper.unmount();
  });

  it("blocks an invalid archive even after a platform is selected", async () => {
    inspectRomUpload.mockResolvedValueOnce({
      ...unknownInspection,
      format: "zip",
      invalid: true,
    });
    const wrapper = await mixedFixture([new File(["zeros"], "bad.zip")]);
    wrapper
      .findAllComponents(stubs.PlatformSelect)[1]!
      .vm.$emit("update:modelValue", "n64");
    await nextTick();
    expect(wrapper.text()).toContain("common.upload-invalid-file");
    expect(
      wrapper.get('[data-testid="upload-submit"]').attributes("disabled"),
    ).toBeDefined();
    wrapper.unmount();
  });

  it("keeps CHD files out of cartridge platforms even when the exact disc is unknown", async () => {
    inspectRomUpload.mockResolvedValueOnce({
      ...unknownInspection,
      format: "chd",
      incompatible_platforms: ["n64"],
    });
    const wrapper = await mixedFixture([new File(["chd"], "Seaman.chd")]);
    wrapper
      .findAllComponents(stubs.PlatformSelect)[1]!
      .vm.$emit("update:modelValue", "n64");
    await nextTick();
    expect(
      wrapper.get('[data-testid="upload-submit"]').attributes("disabled"),
    ).toBeDefined();
    wrapper.unmount();
  });

  it("shows inspection failure and retries without uploading", async () => {
    inspectRomUpload.mockRejectedValueOnce(new Error("offline"));
    const wrapper = await mixedFixture([new File(["data"], "game.zip")]);
    expect(wrapper.text()).toContain("common.upload-inspection-failed");
    expect(
      wrapper.get('[data-testid="upload-submit"]').attributes("disabled"),
    ).toBeDefined();
    inspectRomUpload.mockResolvedValueOnce(detected("genesis"));
    const retry = wrapper
      .findAll("button")
      .find((button) => button.text() === "common.try-again")!;
    await retry.trigger("click");
    await flushPromises();
    expect(
      wrapper.get('[data-testid="upload-submit"]').attributes("disabled"),
    ).toBeUndefined();
    wrapper.unmount();
  });
});
