import { useRef } from "react";
import { useEvents, type LoopEvent } from "./useEvents";
import { Hero } from "./components/Hero";
import { HowItWorks } from "./components/HowItWorks";
import { Console } from "./components/Console";
import { focusSelect } from "./lib/scroll";
import { ByoGuide } from "./components/ByoGuide";
import { SiteFooter } from "./components/SiteFooter";
import "./styles.css";

export default function App() {
  const { events, source } = useEvents();
  const consoleRef = useRef<HTMLElement>(null);
  const byoRef = useRef<HTMLElement>(null);

  const prefersReducedMotion = () =>
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

  const scrollTo = (el: HTMLElement | null, then?: () => void) => {
    if (!el) return;
    el.scrollIntoView({
      behavior: prefersReducedMotion() ? "auto" : "smooth",
      block: "start",
    });
    if (then) window.setTimeout(then, prefersReducedMotion() ? 0 : 500);
  };

  const goToConsole = () =>
    scrollTo(consoleRef.current, () => focusSelect(consoleRef.current));

  const goToGuide = () => scrollTo(byoRef.current);

  const promoted = events.find(
    (e): e is Extract<LoopEvent, { type: "promoted" }> => e.type === "promoted"
  );

  return (
    <div className="shell">
      <a className="skip-link" href="#console-heading">
        Skip to live console
      </a>

      <Hero onRunDemo={goToConsole} onUseOwn={goToGuide} />

      <HowItWorks />

      <Console ref={consoleRef} events={events} source={source} />

      {promoted && (
        <aside className="promoted" role="status">
          <span className="promoted-icon" aria-hidden="true">
            ✓
          </span>
          <div className="promoted-text">
            <strong>Promoted v{promoted.version}</strong>
            <span className="promoted-score">
              {Math.round(promoted.test * 100)}% on held-out test
            </span>
          </div>
        </aside>
      )}

      <ByoGuide ref={byoRef} />

      <SiteFooter onLaunch={goToConsole} />
    </div>
  );
}
