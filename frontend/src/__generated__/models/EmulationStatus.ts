/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EmulationGame } from './EmulationGame';
import type { EmulationPlatform } from './EmulationPlatform';
import type { EmulationSession } from './EmulationSession';
export type EmulationStatus = {
    enabled: boolean;
    updated?: (number | null);
    platforms?: Array<EmulationPlatform>;
    games?: Array<EmulationGame>;
    buttons?: Record<string, string>;
    action_buttons?: Record<string, string>;
    shortcuts?: Record<string, Array<string>>;
    sessions?: Array<EmulationSession>;
};

