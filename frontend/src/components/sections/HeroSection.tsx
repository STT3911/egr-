import { useState } from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Search, ArrowRight, Building2, Shield, Zap } from "lucide-react";

export const HeroSection = () => {
  const [searchQuery, setSearchQuery] = useState("");

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    console.log("Searching for:", searchQuery);
  };

  return (
    <section className="relative min-h-screen flex items-center justify-center gradient-hero overflow-hidden pt-20">
      {/* Background Elements */}
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute top-20 left-10 w-72 h-72 bg-primary/10 rounded-full blur-3xl" />
        <div className="absolute bottom-20 right-10 w-96 h-96 bg-accent/10 rounded-full blur-3xl" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-primary/5 rounded-full blur-3xl" />
      </div>

      <div className="container mx-auto px-4 sm:px-6 relative z-10">
        <div className="max-w-4xl mx-auto text-center">
          {/* Badge */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-full glass shadow-soft mb-8"
          >
            <Zap className="w-4 h-4 text-primary" />
            <span className="text-sm font-medium text-foreground">Данные ЕГР в реальном времени</span>
          </motion.div>

          {/* Headline */}
          <motion.h1
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.1 }}
            className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-bold text-foreground mb-6 leading-tight"
          >
            Вся информация о компаниях{" "}
            <span className="text-gradient">Беларуси</span>
          </motion.h1>

          {/* Subtitle */}
          <motion.p
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.2 }}
            className="text-lg sm:text-xl text-muted-foreground mb-10 max-w-2xl mx-auto"
          >
            Современный сервис для поиска и проверки компаний по данным Единого государственного регистра Республики Беларусь
          </motion.p>

          {/* Search Form */}
          <motion.form
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.3 }}
            onSubmit={handleSearch}
            className="max-w-2xl mx-auto mb-12"
          >
            <div className="relative flex items-center gap-3 p-2 bg-card rounded-2xl shadow-card border border-border">
              <div className="flex-1 flex items-center gap-3 pl-4">
                <Search className="w-5 h-5 text-muted-foreground flex-shrink-0" />
                <Input
                  type="text"
                  placeholder="Введите УНП или название компании"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="border-0 bg-transparent focus-visible:ring-0 focus-visible:ring-offset-0 text-base sm:text-lg placeholder:text-muted-foreground/60"
                />
              </div>
              <Button 
                type="submit"
                size="lg"
                className="gradient-primary text-primary-foreground shadow-soft hover:shadow-glow transition-all px-6 sm:px-8"
              >
                <span className="hidden sm:inline">Найти</span>
                <ArrowRight className="w-5 h-5 sm:ml-2" />
              </Button>
            </div>
          </motion.form>

          {/* Stats */}
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.4 }}
            className="grid grid-cols-2 sm:grid-cols-3 gap-6 sm:gap-8 max-w-xl mx-auto"
          >
            <div className="text-center">
              <div className="text-3xl sm:text-4xl font-bold text-foreground">500K+</div>
              <div className="text-sm text-muted-foreground mt-1">Компаний</div>
            </div>
            <div className="text-center">
              <div className="text-3xl sm:text-4xl font-bold text-foreground">24/7</div>
              <div className="text-sm text-muted-foreground mt-1">Доступность</div>
            </div>
            <div className="text-center col-span-2 sm:col-span-1">
              <div className="text-3xl sm:text-4xl font-bold text-foreground">99.9%</div>
              <div className="text-sm text-muted-foreground mt-1">Точность</div>
            </div>
          </motion.div>
        </div>
      </div>

      {/* Floating Cards */}
      <motion.div
        initial={{ opacity: 0, x: -50 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.8, delay: 0.6 }}
        className="hidden lg:block absolute left-10 top-1/3 animate-float"
      >
        <div className="glass p-4 rounded-xl shadow-card">
          <Building2 className="w-8 h-8 text-primary mb-2" />
          <p className="text-sm font-medium text-foreground">Реестр ЮЛ и ИП</p>
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, x: 50 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.8, delay: 0.7 }}
        className="hidden lg:block absolute right-10 bottom-1/3 animate-float"
        style={{ animationDelay: "1s" }}
      >
        <div className="glass p-4 rounded-xl shadow-card">
          <Shield className="w-8 h-8 text-accent mb-2" />
          <p className="text-sm font-medium text-foreground">Безопасный API</p>
        </div>
      </motion.div>
    </section>
  );
};
