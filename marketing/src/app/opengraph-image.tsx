import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt = "Clariti TMS — the translation system you actually own";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default async function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          background:
            "radial-gradient(800px 400px at 20% 0%, rgba(255,120,71,0.18), transparent 60%), #07080a",
          color: "#ecedf0",
          padding: 72,
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          fontFamily: "Inter, sans-serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div
            style={{
              display: "flex",
              width: 28,
              height: 28,
              borderRadius: 6,
              border: "2px solid #ff7847",
            }}
          />
          <div style={{ display: "flex", alignItems: "baseline", gap: 2, fontSize: 22, letterSpacing: -0.5 }}>
            <span>Clariti</span>
            <span style={{ color: "#7a7e8a" }}>/tms</span>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: 12,
              fontSize: 72,
              lineHeight: 1.02,
              letterSpacing: -3,
              fontWeight: 700,
              maxWidth: 1000,
            }}
          >
            <span>The translation system</span>
            <span style={{ color: "#ff7847" }}>you actually own.</span>
          </div>
          <div style={{ display: "flex", fontSize: 26, color: "#b5b8c1", maxWidth: 900, lineHeight: 1.35 }}>
            <span>
              Self-hosted · AGPL · bring-your-own LLM · screen-batch context · back-translation QA
            </span>
          </div>
        </div>

        <div
          style={{
            display: "flex",
            gap: 18,
            fontFamily: "monospace",
            fontSize: 18,
            color: "#7a7e8a",
          }}
        >
          <span style={{ color: "#ff9970" }}>$</span>
          <span>git clone github.com/clariti-tms/clariti</span>
        </div>
      </div>
    ),
    { ...size },
  );
}
