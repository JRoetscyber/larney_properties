// Wait for the DOM to be fully loaded
document.addEventListener('DOMContentLoaded', function() {
    // Animate elements when they come into view
    function animateOnScroll() {
        const elements = document.querySelectorAll('.animate-on-scroll');
        
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('animated');
                    observer.unobserve(entry.target);
                }
            });
        }, {
            threshold: 0.1
        });
        
        elements.forEach(element => {
            observer.observe(element);
        });
    }
    
    // Initialize animations
    animateOnScroll();
    
    // Animate hero shape backgrounds
    function animateHeroShapes() {
        const shapes = document.querySelectorAll('.shape');
        
        shapes.forEach(shape => {
            // Random starting position
            const randomX = Math.random() * 20 - 10;
            const randomY = Math.random() * 20 - 10;
            
            // Set initial position
            shape.style.transform = `translate(${randomX}px, ${randomY}px)`;
            
            // Animate the shape continuously
            setInterval(() => {
                const newX = Math.random() * 20 - 10;
                const newY = Math.random() * 20 - 10;
                
                shape.style.transition = 'transform 5s ease-in-out';
                shape.style.transform = `translate(${newX}px, ${newY}px)`;
            }, 5000);
        });
    }
    
    // Call the function
    animateHeroShapes();
});

// Add this to your existing animations.js file

// Animate skill progress bars
function animateSkillBars() {
    const progressBars = document.querySelectorAll('.skill-progress');
    
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const progressBar = entry.target;
                const progress = progressBar.getAttribute('data-progress');
                progressBar.style.transform = `scaleX(${progress / 100})`;
                observer.unobserve(progressBar);
            }
        });
    }, {
        threshold: 0.1
    });
    
    progressBars.forEach(bar => {
        observer.observe(bar);
    });
}

// Call this function after DOM content is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Your existing code...
    
    // Add the animate on scroll functionality
    const animatedElements = document.querySelectorAll('.animate-on-scroll');
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('animated');
                observer.unobserve(entry.target);
            }
        });
    }, {
        threshold: 0.1
    });
    
    animatedElements.forEach(element => {
        observer.observe(element);
    });
    
    // Call the skill bar animation
    animateSkillBars();
});