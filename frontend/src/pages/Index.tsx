import { Header } from "@/components/layout/Header";
import { Footer } from "@/components/layout/Footer";
import { HeroSection } from "@/components/sections/HeroSection";
import { FeaturesSection } from "@/components/sections/FeaturesSection";
import { AboutSection } from "@/components/sections/AboutSection";
import { CTASection } from "@/components/sections/CTASection";
import { AscendEarth } from "@/components/sections/AscendEarth";
import "./ascend.css";

const Index = () => {
  return (
    <div id="page-top" className="ascend-home min-h-screen bg-background">
      <AscendEarth />
      <Header />

      <main>
        <HeroSection />
        <FeaturesSection />
        <AboutSection />
        <CTASection />
      </main>

      <Footer />
    </div>
  );
};

export default Index;
