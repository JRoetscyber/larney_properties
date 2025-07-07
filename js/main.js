// Wait for the DOM to be fully loaded
document.addEventListener('DOMContentLoaded', function() {
    // Initialize EmailJS
    (function() {
        emailjs.init('degXCNYEDAW_NZvRs');
    })();
    
    // Theme toggle functionality
    const themeToggle = document.querySelector('.theme-toggle');
    const body = document.body;
    
    // Check for saved theme preference
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {
        body.classList.add('dark-mode');
        themeToggle.querySelector('i').classList.replace('fa-moon', 'fa-sun');
    }
    
    // Toggle theme on click
    themeToggle.addEventListener('click', function() {
        body.classList.toggle('dark-mode');
        
        // Update icon
        const icon = themeToggle.querySelector('i');
        if (body.classList.contains('dark-mode')) {
            icon.classList.replace('fa-moon', 'fa-sun');
            localStorage.setItem('theme', 'dark');
        } else {
            icon.classList.replace('fa-sun', 'fa-moon');
            localStorage.setItem('theme', 'light');
        }
    });
    
    // Mobile navigation toggle
    const hamburger = document.querySelector('.hamburger');
    const navLinks = document.querySelector('.nav-links');
    
    hamburger.addEventListener('click', function() {
        navLinks.classList.toggle('active');
        hamburger.classList.toggle('active');
    });
    
    // Close mobile menu when a link is clicked
    document.querySelectorAll('.nav-links a').forEach(link => {
        link.addEventListener('click', function() {
            navLinks.classList.remove('active');
            hamburger.classList.remove('active');
        });
    });
});

// Change navbar style on scroll
window.addEventListener('scroll', function() {
    const navbar = document.querySelector('nav');
    if (window.scrollY > 50) {
        navbar.classList.add('scrolled');
    } else {
        navbar.classList.remove('scrolled');
    }
});

// Smooth scrolling for navigation links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
        e.preventDefault();
        const targetId = this.getAttribute('href');
        const targetElement = document.querySelector(targetId);
        
        if (targetElement) {
            window.scrollTo({
                top: targetElement.offsetTop - 100,
                behavior: 'smooth'
            });
        }
    });
});

// Project filtering functionality
function setupProjectFilters() {
    const filterBtns = document.querySelectorAll('.filter-btn');
    const projectCards = document.querySelectorAll('.project-card');
    
    filterBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            // Remove active class from all buttons
            filterBtns.forEach(btn => btn.classList.remove('active'));
            
            // Add active class to clicked button
            this.classList.add('active');
            
            // Get the filter value
            const filterValue = this.getAttribute('data-filter');
            
            // Filter the projects
            projectCards.forEach(card => {
                const categories = card.getAttribute('data-category');
                
                // Add animation classes for smooth transitions
                card.classList.add('animate-filter');
                
                // Split categories by comma or space and trim whitespace
                const categoryArray = categories.split(/[,\s]+/).map(cat => cat.trim().toLowerCase());
                
                if (filterValue === 'all' || categoryArray.includes(filterValue.toLowerCase())) {
                    card.classList.remove('hide');
                    setTimeout(() => {
                        card.classList.remove('animate-filter');
                    }, 300);
                } else {
                    card.classList.add('hide');
                }
            });
        });
    });
}

// Call this function after DOM content is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Setup project filters
    setupProjectFilters();
});

// Timeline tab functionality
function setupTimelineTabs() {
    const timelineTabs = document.querySelectorAll('.timeline-tab');
    const timelines = document.querySelectorAll('.timeline');
    
    timelineTabs.forEach(tab => {
        tab.addEventListener('click', function() {
            // Remove active class from all tabs
            timelineTabs.forEach(tab => tab.classList.remove('active'));
            
            // Add active class to clicked tab
            this.classList.add('active');
            
            // Get the tab value
            const tabValue = this.getAttribute('data-tab');
            
            // Hide all timelines and show the selected one
            timelines.forEach(timeline => {
                if (timeline.id === `${tabValue}-timeline`) {
                    timeline.classList.add('active');
                    
                    // Reset animations
                    const items = timeline.querySelectorAll('.timeline-item');
                    items.forEach((item, index) => {
                        setTimeout(() => {
                            item.classList.add('animated');
                        }, 100 * index);
                    });
                } else {
                    timeline.classList.remove('active');
                    timeline.querySelectorAll('.timeline-item').forEach(item => {
                        item.classList.remove('animated');
                    });
                }
            });
        });
    });
    
    // Initialize the first tab
    const firstTimelineItems = document.querySelector('.timeline.active').querySelectorAll('.timeline-item');
    firstTimelineItems.forEach((item, index) => {
        setTimeout(() => {
            item.classList.add('animated');
        }, 500 + (100 * index)); // Add a delay for initial load
    });
}

// Call this function after DOM content is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Setup timeline tabs
    setupTimelineTabs();
});

// Form submission handling
function submitForm(event) {
    event.preventDefault();
    
    // Get form values using the correct IDs from your HTML
    const name = document.getElementById('name').value.trim();
    const email = document.getElementById('email').value.trim();
    const subject = document.getElementById('subject').value.trim();
    const message = document.getElementById('message').value.trim();
    
    // Get form message display element
    const formSuccess = document.getElementById('formSuccess');
    const submitButton = document.querySelector('.form-submit');
    
    // Validation
    if (!name || !email || !subject || !message) {
        alert('Please fill in all fields.');
        return false;
    }
    
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        alert('Please enter a valid email address.');
        return false;
    }
    
    // Show loading state
    submitButton.innerHTML = '<span class="submit-text">Sending...</span>';
    submitButton.disabled = true;
    
    // Add time and year variables
    const now = new Date();
    const time = now.toLocaleString();
    const year = now.getFullYear();
    
    const serviceID = "service_56xmdu2";
    const templateID = "template_23pzg8u";
    
    // Send emails using EmailJS
    Promise.all([
        emailjs.send(serviceID, templateID, {
            from_name: name,
            from_email: email,
            title: subject,
            message: message,
            time: time,
            year: year
        }),
        emailjs.send('service_56xmdu2', 'template_vc2ninu', {
            from_name: name,
            title: subject,
            from_email: email,
            year: year,
            email: email
        })
    ])
    .then(
        res => {
            // Show success message
            formSuccess.classList.add('active');
            
            // Reset form
            document.getElementById('contactForm').reset();
            
            // Reset button
            submitButton.innerHTML = '<span class="submit-text">Send Message</span><span class="submit-icon"><i class="fas fa-paper-plane"></i></span>';
            submitButton.disabled = false;
        },
        error => {
            console.error('EmailJS send failed:', error);
            alert('Failed to send email. Please try again later.');
            
            // Reset button
            submitButton.innerHTML = '<span class="submit-text">Send Message</span><span class="submit-icon"><i class="fas fa-paper-plane"></i></span>';
            submitButton.disabled = false;
        }
    );
    
    return false;
}

// Reset form after successful submission
function resetForm() {
    document.getElementById('formSuccess').classList.remove('active');
}

// Set current year in footer
document.addEventListener('DOMContentLoaded', function() {
    // Set current year
    const currentYearElement = document.getElementById('currentYear');
    if (currentYearElement) {
        currentYearElement.textContent = new Date().getFullYear();
    }
});