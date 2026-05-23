import { ImageResponse } from "next/og";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

// Apple touch icon — same mark as the favicon, scaled for iOS home-screen
// pins (180×180). Indigo flame background with the ClaritiTMS line mark in
// white. Generated at build time via next/og's ImageResponse.
export default function AppleIcon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#4f46e5",
        }}
      >
        <svg width="120" height="120" viewBox="0 0 32 32" fill="none">
          <path
            d="M9 11h10M9 16h14M9 21h7"
            stroke="#ffffff"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
          <circle cx="24" cy="21" r="1.8" fill="#ffffff" />
        </svg>
      </div>
    ),
    { ...size },
  );
}
