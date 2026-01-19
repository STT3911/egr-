import { useState } from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Menu, X } from "lucide-react";
import { Link } from "react-router-dom";

export const Header = () => {
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  return (
    <motion.header 
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5 }}
      className="fixed top-0 left-0 right-0 z-50 glass"
    >
      <div className="container mx-auto px-4 sm:px-6">
        <div className="flex items-center justify-between h-16 sm:h-20">
          {/* Logo */}
          <Link to="/" className="flex items-center gap-2">
            <div className="w-8 h-8 sm:w-10 sm:h-10 gradient-primary rounded-lg flex items-center justify-center">
              <span className="text-primary-foreground font-bold text-lg sm:text-xl">S</span>
            </div>
            <span className="text-xl sm:text-2xl font-bold text-foreground">Service</span>
          </Link>

          {/* Desktop Navigation */}
          <nav className="hidden md:flex items-center gap-8">
            <a href="#features" className="text-muted-foreground hover:text-foreground transition-colors">
              Возможности
            </a>
            <a href="#about" className="text-muted-foreground hover:text-foreground transition-colors">
              О сервисе
            </a>
            <a href="#pricing" className="text-muted-foreground hover:text-foreground transition-colors">
              Тарифы
            </a>
          </nav>

          {/* Desktop Auth Buttons */}
          <div className="hidden md:flex items-center gap-3">
            <Link to="/login">
              <Button variant="ghost" className="text-muted-foreground hover:text-foreground">
                Войти
              </Button>
            </Link>
            <Link to="/register">
              <Button className="gradient-primary text-primary-foreground shadow-soft hover:shadow-glow transition-shadow">
                Регистрация
              </Button>
            </Link>
          </div>

          {/* Mobile Menu Button */}
          <button 
            className="md:hidden p-2"
            onClick={() => setIsMenuOpen(!isMenuOpen)}
          >
            {isMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>
        </div>

        {/* Mobile Menu */}
        {isMenuOpen && (
          <motion.div 
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="md:hidden py-4 border-t border-border"
          >
            <nav className="flex flex-col gap-4">
              <a href="#features" className="text-muted-foreground hover:text-foreground transition-colors py-2">
                Возможности
              </a>
              <a href="#about" className="text-muted-foreground hover:text-foreground transition-colors py-2">
                О сервисе
              </a>
              <a href="#pricing" className="text-muted-foreground hover:text-foreground transition-colors py-2">
                Тарифы
              </a>
              <div className="flex flex-col gap-2 pt-4 border-t border-border">
                <Link to="/login">
                  <Button variant="outline" className="w-full">Войти</Button>
                </Link>
                <Link to="/register">
                  <Button className="w-full gradient-primary text-primary-foreground">Регистрация</Button>
                </Link>
              </div>
            </nav>
          </motion.div>
        )}
      </div>
    </motion.header>
  );
};
