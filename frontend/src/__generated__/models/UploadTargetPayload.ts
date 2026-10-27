/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Optional body of `/start`: upload into a ROM's folder instead of the
 * platform folder, and name the file where the header cannot.
 */
export type UploadTargetPayload = {
    /**
     * Upload into this ROM's folder instead of the platform folder.
     */
    rom_id?: (number | null);
    /**
     * Relative subfolder inside the platform, or inside the ROM when rom_id is set. Empty for the root.
     */
    folder?: string;
    /**
     * Game folder upload to stage this file in until all files finish.
     */
    batch_id?: (string | null);
    /**
     * The file name. Takes precedence over the header, which cannot carry characters outside Latin-1.
     */
    filename?: (string | null);
    /**
     * Replace a file of the same name in the ROM's folder instead of refusing the upload.
     */
    overwrite?: boolean;
};

