declare module 'qrcode' {
  interface QRCodeOptions {
    width?: number;
    margin?: number;
    color?: {
      dark?: string;
      light?: string;
    };
  }
  function toCanvas(
    canvas: HTMLCanvasElement,
    text: string,
    options?: QRCodeOptions
  ): Promise<void>;
}
