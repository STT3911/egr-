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

        {/* Section Divider */}
        <div className="relative h-24 bg-gradient-to-b from-background via-background/80 to-background">
          <div className="absolute inset-0 bg-gradient-to-r from-primary/5 via-transparent to-accent/5" />
          <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-px h-12 bg-gradient-to-b from-primary/20 to-transparent" />
        </div>

        <div className="relative">
          <div className="absolute inset-0 bg-gradient-to-b from-transparent via-background/50 to-background pointer-events-none" />
          <FeaturesSection />
        </div>

        {/* Section Divider */}
        <div className="relative h-24 bg-gradient-to-b from-background via-secondary/30 to-background">
          <div className="absolute inset-0 bg-gradient-to-r from-accent/5 via-transparent to-primary/5" />
          <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-px h-12 bg-gradient-to-b from-accent/20 to-transparent" />
        </div>

        <div className="relative">
          <div className="absolute inset-0 bg-gradient-to-b from-transparent via-secondary/30 to-transparent pointer-events-none" />
          <AboutSection />
        </div>

        {/* Section Divider */}
        <div className="relative h-24 bg-gradient-to-b from-background via-background/80 to-background">
          <div className="absolute inset-0 bg-gradient-to-r from-primary/5 via-transparent to-accent/5" />
          <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-px h-12 bg-gradient-to-b from-primary/20 to-transparent" />
        </div>

        <div className="relative">
          <div className="absolute inset-0 bg-gradient-to-b from-transparent via-background/50 to-background pointer-events-none" />
          <CTASection />
        </div>
      </main>
      <Footer />
    </div>
  );
};

export default Index;
