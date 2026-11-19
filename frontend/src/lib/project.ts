/** The site's name and one-line description, shown in the header, home page and footer. */
export const SITE = {
  name: 'StegaGuard',
  tagline: 'Hide messages in images, prove who sent them, and detect what is hidden.',
} as const;

/** Plain names for the detectors; the results file keeps its own technical labels. */
export const DETECTOR_NAMES: Record<string, string> = {
  statistical: 'Statistical tests',
  classical: 'Feature-based classifier',
  rf: 'Feature-based classifier',
  cnn: 'Neural network',
  cnn_v1: 'Neural network',
  ensemble: 'Combined (classifier + network)',
};
