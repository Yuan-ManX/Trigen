import Navbar from "@/components/Navbar";
import Hero from "@/components/Hero";
import Innovation from "@/components/Innovation";
import Features from "@/components/Features";
import UseCases from "@/components/UseCases";
import CTA from "@/components/CTA";
import Footer from "@/components/Footer";

export default function Home() {
  return (
    <div className="relative min-h-screen bg-ink">
      <Navbar />
      <main>
        <Hero />
        <Innovation />
        <Features />
        <UseCases />
        <CTA />
      </main>
      <Footer />
    </div>
  );
}
