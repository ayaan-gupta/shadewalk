declare module 'gifenc' {
  type Palette = number[][]
  interface Encoder {
    writeFrame(index: Uint8Array, width: number, height: number, opts: Record<string, unknown>): void
    finish(): void
    bytes(): Uint8Array
  }
  const gifenc: {
    GIFEncoder(): Encoder
    quantize(rgba: Uint8Array, maxColors: number): Palette
    applyPalette(rgba: Uint8Array, palette: Palette): Uint8Array
  }
  export default gifenc
}
