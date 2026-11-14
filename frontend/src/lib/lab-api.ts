import { analyzeImage, ApiError, validateFile, type Perception } from './api';

export type LabPerceiver = (
    image: Blob,
    dimensions: { width: number; height: number },
    signal: AbortSignal,
) => Promise<Perception>;

export function apiLabPerceiver(base: string): LabPerceiver {
    return async (image, dimensions, signal) => {
        signal.throwIfAborted();
        const file =
            image instanceof File
                ? image
                : new File([image], 'controller-capture.png', { type: image.type });
        validateFile(file);
        const result = await analyzeImage(base, file, dimensions, signal);
        signal.throwIfAborted();
        if (result.model_name !== 'lab-color-api-v1')
            throw new ApiError(
                'Le serveur n’annonce pas le pipeline du laboratoire. Activer SBC_PERCEPTION_MODE=lab-colors.',
                'wrong_perception_mode',
            );
        return result;
    };
}
