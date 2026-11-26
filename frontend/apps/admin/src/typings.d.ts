/// <reference types="vite/client" />

declare module '*.css';
declare module '*.less';
declare module '*.scss';
declare module '*.sass';
declare module '*.svg';
declare module '*.png';
declare module '*.jpg';
declare module '*.jpeg';
declare module '*.gif';
declare module '*.bmp';
declare module '*.tiff';
declare module '*.md' {
  const content: string;
  export default content;
}

declare const __APP_VERSION__: string;
declare const __REACT_VERSION__: string;
declare const __VITE_VERSION__: string;

declare const process: { env: Record<string, string | undefined> };
