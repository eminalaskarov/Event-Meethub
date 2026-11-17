import { Html5Qrcode } from "html5-qrcode";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

const ELEMENT_ID = "ticket-qr-reader";

export default function CameraScanner({ onDecode }: { onDecode: (text: string) => void }) {
  const { t } = useTranslation();
  const onDecodeRef = useRef(onDecode);
  const lifecycle = useRef<Promise<void>>(Promise.resolve());
  const [failed, setFailed] = useState(false);

  onDecodeRef.current = onDecode;

  useEffect(() => {
    let scanner: Html5Qrcode | null = null;
    let running = false;

    // Serializing start and stop keeps React StrictMode from opening two cameras.
    lifecycle.current = lifecycle.current.then(async () => {
      try {
        scanner = new Html5Qrcode(ELEMENT_ID);
        await scanner.start(
          { facingMode: "environment" },
          { fps: 10, qrbox: { width: 240, height: 240 } },
          (text) => onDecodeRef.current(text),
          () => undefined,
        );
        running = true;
        setFailed(false);
      } catch {
        setFailed(true);
      }
    });

    return () => {
      lifecycle.current = lifecycle.current.then(async () => {
        try {
          if (scanner && running) await scanner.stop();
          scanner?.clear();
        } catch {
          // The element may already be gone when leaving the page.
        }
      });
    };
  }, []);

  return (
    <div>
      <div id={ELEMENT_ID} className="mx-auto w-full max-w-sm overflow-hidden rounded-xl bg-black" />
      {failed && <div className="alert-error mt-3">{t("scanner.cameraError")}</div>}
    </div>
  );
}