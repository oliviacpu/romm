import { RForm } from "@v2/lib";
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  EmulationProfileResponse,
  EmulationStatus,
} from "@/__generated__";
import EmulationSection from "@/v2/components/Settings/EmulationSection.vue";

const { status, profile, save, success, error } = vi.hoisted(() => ({
  status: vi.fn(),
  profile: vi.fn(),
  save: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}));
vi.mock("@/services/api/emulation", () => ({
  default: { status, profile, save },
}));
vi.mock("vue-i18n");
vi.mock("@/v2/composables/useRouteQueryParam", async () => {
  const { ref } = await import("vue");
  return { useRouteQueryParam: (_key: string, fallback = "") => ref(fallback) };
});
vi.mock("@/v2/composables/useSnackbar", () => ({
  useSnackbar: () => ({ success, error }),
}));

function listing(): EmulationStatus {
  return {
    enabled: true,
    updated: Date.now() / 1000,
    platforms: [
      {
        id: "ps2",
        label: "PlayStation 2",
        buttons: { a: "Cross", b: "Circle", x: "Square" },
        mapping: true,
        widescreen: true,
        resolutions: ["native", "1080p"],
      },
    ],
    games: [{ id: "a".repeat(20), system: "ps2", title: "SSX Tricky" }],
    buttons: { a: "A", b: "B", x: "X" },
    action_buttons: { share: "Share", l3: "Left stick click", menu: "Menu" },
    shortcuts: { share: ["share"], l3_menu: ["l3", "menu"], none: [] },
    sessions: [
      {
        id: "session-one",
        system: "ps2",
        game: "SSX Tricky",
        started: 1,
        ended: 2,
        messages: [
          {
            timestamp: 1,
            source: "PCSX2",
            level: "warning",
            text: "Blending accuracy is below the recommended level.",
          },
        ],
      },
    ],
  };
}

function settings(): EmulationProfileResponse {
  const inherited = {
    resolution: "native" as const,
    aspect: "original" as const,
    osd_scale: 200,
    bindings: { a: "a", b: "b", x: "x" },
    menu_shortcut: "share",
    quit_shortcut: "l3_menu",
  };
  return {
    revision: 2,
    saved: { bindings: {} },
    inherited,
    effective: inherited,
  };
}

async function mountSection() {
  const wrapper = mount(EmulationSection, {
    global: { stubs: { RIcon: true } },
  });
  await flushPromises();
  return wrapper;
}

describe("Sunshine emulation profiles", () => {
  beforeEach(() => {
    status.mockReset().mockResolvedValue({ data: listing() });
    profile.mockReset().mockResolvedValue({ data: settings() });
    save.mockReset().mockResolvedValue({ data: settings() });
    success.mockReset();
    error.mockReset();
  });

  it("keeps the source and warning visible after the session ended", async () => {
    const wrapper = await mountSection();
    expect(wrapper.text()).toContain("PCSX2");
    expect(wrapper.text()).toContain(
      "Blending accuracy is below the recommended level.",
    );
    expect(wrapper.text()).toContain("emulation.shortcuts");
    wrapper.unmount();
  });

  it("swaps assignments and saves the selected platform with its revision", async () => {
    const wrapper = await mountSection();
    const circle = wrapper
      .findAllComponents({ name: "RSelect" })
      .find((select) => select.props("label") === "Circle");
    expect(circle).toBeDefined();
    circle?.vm.$emit("update:modelValue", "x");
    await flushPromises();
    wrapper.findComponent(RForm).vm.$emit("submit", new Event("submit"));
    await flushPromises();
    expect(save).toHaveBeenCalledWith("ps2", null, {
      revision: 2,
      profile: { bindings: { b: "x", x: "b" } },
    });
    expect(success).toHaveBeenCalledWith("emulation.saved");
    wrapper.unmount();
  });

  it("reports a failed save and allows retrying without losing the draft", async () => {
    save.mockRejectedValueOnce(new Error("conflict"));
    const wrapper = await mountSection();
    wrapper.findComponent(RForm).vm.$emit("submit", new Event("submit"));
    await flushPromises();
    expect(error).toHaveBeenCalledWith("emulation.save-failed");
    wrapper.findComponent(RForm).vm.$emit("submit", new Event("submit"));
    await flushPromises();
    expect(save).toHaveBeenCalledTimes(2);
    wrapper.unmount();
  });

  it("reloads a failed profile request through the refresh action", async () => {
    profile.mockRejectedValueOnce(new Error("offline"));
    const wrapper = await mountSection();
    expect(wrapper.text()).toContain("emulation.unavailable");
    const refresh = wrapper.find("button");
    await refresh.trigger("click");
    await flushPromises();
    expect(wrapper.findComponent(RForm).exists()).toBe(true);
    wrapper.unmount();
  });

  it("opens a dropdown with Enter without submitting settings", async () => {
    const wrapper = await mountSection();
    const field = wrapper
      .findComponent(RForm)
      .find('button[aria-haspopup="listbox"]');
    await field.trigger("keydown", { key: "Enter" });
    await flushPromises();
    expect(save).not.toHaveBeenCalled();
    expect(field.attributes("aria-expanded")).toBe("true");
    wrapper.unmount();
  });

  it("does not render settings when the integration is disabled", async () => {
    status.mockResolvedValue({ data: { enabled: false } });
    const wrapper = await mountSection();
    expect(wrapper.text()).toContain("emulation.not-configured");
    expect(profile).not.toHaveBeenCalled();
    expect(wrapper.findComponent(RForm).exists()).toBe(false);
    wrapper.unmount();
  });
});
