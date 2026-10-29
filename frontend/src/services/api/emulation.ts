import type {
  EmulationProfileRequest,
  EmulationProfileResponse,
  EmulationStatus,
} from "@/__generated__";
import api from "@/services/api";

export default {
  status: () => api.get<EmulationStatus>("/emulation"),
  profile: (system: string, gameId: string | null) =>
    api.get<EmulationProfileResponse>(
      `/emulation/profiles/${encodeURIComponent(system)}`,
      { params: { game_id: gameId || undefined } },
    ),
  save: (
    system: string,
    gameId: string | null,
    payload: EmulationProfileRequest,
  ) =>
    api.put<EmulationProfileResponse>(
      `/emulation/profiles/${encodeURIComponent(system)}`,
      payload,
      { params: { game_id: gameId || undefined } },
    ),
};
