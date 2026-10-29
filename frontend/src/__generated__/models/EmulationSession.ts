/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EmulationMessage } from './EmulationMessage';
export type EmulationSession = {
    id: string;
    system: string;
    game: string;
    started: number;
    ended?: (number | null);
    messages: Array<EmulationMessage>;
};

