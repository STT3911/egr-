import { Header } from "@/components/layout/Header";
import { Footer } from "@/components/layout/Footer";
import { HeroSection } from "@/components/sections/HeroSection";
import { FeaturesSection } from "@/components/sections/FeaturesSection";
import { AboutSection } from "@/components/sections/AboutSection";
import { CTASection } from "@/components/sections/CTASection";

const Index = () => {
  return (
    <div id="page-top" className="min-h-screen bg-background">
      <Header />

      <main>
        <HeroSection />

        <div className="container mx-auto max-w-6xl px-4 sm:px-6">
          <div className="section-divider" />
        </div>

        <FeaturesSection />

        <div className="container mx-auto max-w-6xl px-4 sm:px-6">
          <div className="section-divider" />
        </div>

        <AboutSection />

        <div className="container mx-auto max-w-6xl px-4 sm:px-6">
          <div className="section-divider" />
        </div>

        <CTASection />
      </main>

      <Footer />
    </div>
  );
};

export default Index;
