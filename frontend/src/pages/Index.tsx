import { Header } from "@/components/layout/Header";
import { useState, useEffect } from "react";
import { Moon, Sun } from "lucide-react";
import { Footer } from "@/components/layout/Footer";
import { HeroSection } from "@/components/sections/HeroSection";
import { FeaturesSection } from "@/components/sections/FeaturesSection";
import { AboutSection } from "@/components/sections/AboutSection";
import { CTASection } from "@/components/sections/CTASection";

const Index = () => {
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    const theme = localStorage.getItem("theme");
    const systemPrefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;

    if (theme === "dark" || (!theme && systemPrefersDark)) {
      setIsDark(true);
      document.documentElement.classList.add("dark");
    } else {
      setIsDark(false);
      document.documentElement.classList.remove("dark");
    }
  }, []);

  const toggleTheme = () => {
    const newTheme = !isDark;
    setIsDark(newTheme);
    localStorage.setItem("theme", newTheme ? "dark" : "light");

    if (newTheme) {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Floating Theme Toggle */}
      <button
        onClick={toggleTheme}
        className="fixed top-6 right-6 z-50 w-12 h-12 rounded-full glass shadow-card hover:shadow-glow transition-all duration-300 flex items-center justify-center"
        aria-label="Переключить тему"
      >
        {isDark ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
      </button>

      <main className="scroll-smooth">
        <HeroSection />

        {/* Smooth Section Transition */}
        <div className="relative h-32 bg-gradient-to-b from-background via-background/95 to-background/90">
          <div className="absolute inset-0 bg-gradient-to-r from-primary/[0.02] via-transparent to-accent/[0.02]" />
        </div>

        <FeaturesSection />

        {/* Smooth Section Transition */}
        <div className="relative h-32 bg-gradient-to-b from-background/90 via-background/95 to-background">
          <div className="absolute inset-0 bg-gradient-to-r from-accent/[0.02] via-transparent to-primary/[0.02]" />
        </div>

        <AboutSection />

        {/* Smooth Section Transition */}
        <div className="relative h-32 bg-gradient-to-b from-background via-background/95 to-background/90">
          <div className="absolute inset-0 bg-gradient-to-r from-primary/[0.02] via-transparent to-accent/[0.02]" />
        </div>

        <CTASection />
      </main>
    </div>
  );
};

export default Index;
