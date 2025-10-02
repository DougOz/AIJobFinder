import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { initializeApp } from 'firebase/app';
import { 
    getAuth, signInAnonymously, signInWithCustomToken, 
    onAuthStateChanged 
} from 'firebase/auth';
import { 
    getFirestore, doc, setDoc, collection, query, 
    onSnapshot, serverTimestamp 
} from 'firebase/firestore';

// --- Global Setup (Mandatory for Canvas Environment) ---
const firebaseConfig = typeof __firebase_config !== 'undefined' ? JSON.parse(__firebase_config) : {};
const initialAuthToken = typeof __initial_auth_token !== 'undefined' ? __initial_auth_token : null;
const appId = typeof __app_id !== 'undefined' ? __app_id : 'job-trainer-default';

// Initialize Firebase services outside the component to avoid re-initialization
let app, db, auth;
try {
    if (Object.keys(firebaseConfig).length > 0) {
        app = initializeApp(firebaseConfig);
        db = getFirestore(app);
        auth = getAuth(app);
    }
} catch (error) {
    console.error("Firebase initialization failed:", error);
}

// --- Mock Job Data (Replace with your 3724 jobs) ---
const MOCK_JOBS = [
    { id: 'job_001', title: "Senior Python Backend Engineer", skills: ["Python", "Django", "PostgreSQL", "AWS"], 
      description: "We are seeking a highly skilled Senior Python Backend Engineer to lead our API development team. This role requires deep expertise in scalable cloud architecture, particularly using AWS services like S3 and EC2. You will be responsible for designing and implementing robust, high-performance APIs. Experience with real-time data processing and asynchronous tasks is a major plus. The ideal candidate thrives in a collaborative, fast-paced environment and is passionate about code quality and mentorship. Experience with Go or Rust is beneficial." },
    { id: 'job_002', title: "Frontend Developer (React/TS)", skills: ["React", "TypeScript", "Tailwind CSS", "Redux"], 
      description: "Join our team to build the next generation of user interfaces. We focus on modern React with TypeScript and heavy use of Tailwind for aesthetic, responsive design. You must have a strong portfolio demonstrating expertise in component state management and performance optimization. This role is highly collaborative, working closely with UX/UI designers. Database knowledge is not essential, but a basic understanding of RESTful services is required." },
    { id: 'job_003', title: "Java Enterprise Architect", skills: ["Java", "Spring Boot", "JPA", "Microservices"], 
      description: "A large enterprise is looking for an Architect to modernize their legacy systems using Java and Spring Boot. This involves designing microservice architectures and handling massive transaction loads. Familiarity with Kafka and containerization (Docker/Kubernetes) is mandatory. Strong communication skills are required for stakeholder management." },
];

// --- API Helper Function (Simulates Initial Matching Model) ---

/**
 * Calls the Gemini API to calculate an initial fit score and extract relevant terms.
 * This simulates the Python model's function (Vector Similarity/TF-IDF)
 */
const calculateSimilarityScore = async (resumeText, jobTitle, jobDescription) => {
    if (!resumeText || !jobDescription) return { score: 0, summary: "Missing resume or description." };

    const systemPrompt = `You are a job matching expert. Compare the provided RESUME against the JOB POSTING. Provide a FIT_SCORE on a scale of 1 to 100 based on technical and experience overlap. Also, extract three key LIKED phrases (skills/experience matches) and three DISLIKED phrases (major skill gaps or mismatched requirements) from the job description based on the resume.`;
    const userQuery = `RESUME:\n---\n${resumeText}\n---\n\nJOB POSTING TITLE: ${jobTitle}\nJOB POSTING DESCRIPTION:\n---\n${jobDescription}`;

    // Define the structured JSON output schema
    const payload = {
        contents: [{ parts: [{ text: userQuery }] }],
        systemInstruction: { parts: [{ text: systemPrompt }] },
        generationConfig: {
            responseMimeType: "application/json",
            responseSchema: {
                type: "OBJECT",
                properties: {
                    FIT_SCORE: { type: "NUMBER", description: "The calculated fit score (1-100)." },
                    JUSTIFICATION: { type: "STRING", description: "A brief reason for the score." },
                    LIKED_PHRASES: { type: "ARRAY", items: { type: "STRING" }, description: "3 phrases from the description that match the resume." },
                    DISLIKED_PHRASES: { type: "ARRAY", items: { type: "STRING" }, description: "3 phrases from the description that represent a gap or mismatch." }
                },
                required: ["FIT_SCORE", "JUSTIFICATION", "LIKED_PHRASES", "DISLIKED_PHRASES"]
            }
        }
    };
    
    const apiKey = ""; // Canvas environment provides this at runtime
    const apiUrl = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key=${apiKey}`;

    try {
        const response = await fetch(apiUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const result = await response.json();
        const jsonText = result?.candidates?.[0]?.content?.parts?.[0]?.text;
        
        if (jsonText) {
            const parsedJson = JSON.parse(jsonText);
            return {
                score: parsedJson.FIT_SCORE || 0,
                summary: parsedJson.JUSTIFICATION || "Analysis complete.",
                liked_phrases: parsedJson.LIKED_PHRASES || [],
                disliked_phrases: parsedJson.DISLIKED_PHRASES || []
            };
        }
        console.error("Gemini response was empty or malformed:", result);
        return { score: 0, summary: "Error processing model output." };

    } catch (e) {
        console.error("Gemini API call failed:", e);
        // Implement exponential backoff here in a production environment
        return { score: 0, summary: `API Error: ${e.message}` };
    }
};

// --- React Component ---

const App = () => {
    // --- State Management ---
    const [userId, setUserId] = useState(null);
    const [isAuthReady, setIsAuthReady] = useState(false);
    const [resumeText, setResumeText] = useState("");
    
    // Training Data State
    const [jobs, setJobs] = useState([]);
    const [jobIndex, setJobIndex] = useState(0);
    const [filterPercent, setFilterPercent] = useState(25); // Top 25% filter
    
    // Current Job Annotation State
    const [currentScore, setCurrentScore] = useState(5); // 1-10 user score
    const [currentNotes, setCurrentNotes] = useState("");
    const [currentLikedPhrases, setCurrentLikedPhrases] = useState([]);
    const [currentDislikedPhrases, setCurrentDislikedPhrases] = useState([]);
    
    // Model-generated Analysis State
    const [modelScore, setModelScore] = useState(0); 
    const [modelSummary, setModelSummary] = useState("Awaiting resume input...");
    const [isProcessing, setIsProcessing] = useState(false);

    // --- Firebase Auth & Setup ---
    useEffect(() => {
        if (!auth) return;
        
        const signIn = async () => {
            try {
                if (initialAuthToken) {
                    await signInWithCustomToken(auth, initialAuthToken);
                } else {
                    await signInAnonymously(auth);
                }
            } catch (error) {
                console.error("Authentication Error:", error);
            }
        };

        const unsubscribe = onAuthStateChanged(auth, (user) => {
            if (user) {
                setUserId(user.uid);
            } else {
                setUserId(crypto.randomUUID()); // Anonymous ID fallback
            }
            setIsAuthReady(true);
        });

        signIn();
        return () => unsubscribe();
    }, []);

    // --- Data Fetching (Simulated Jobs and Real Training Data) ---
    const currentJob = useMemo(() => jobs[jobIndex] || null, [jobs, jobIndex]);
    const collectionPath = `artifacts/${appId}/users/${userId}/job_training_data`;

    // 1. Load mock jobs initially
    useEffect(() => {
        // In a real app, this would be an onSnapshot or getDocs call to load 
        // the 3724 jobs you scraped.
        const jobsWithMockScores = MOCK_JOBS.map(job => ({
            ...job,
            // Mock Model Score (MOCK_JOBS[0] is a high match, MOCK_JOBS[2] is a low match)
            model_score: job.id === 'job_001' ? 95 : (job.id === 'job_002' ? 65 : 30)
        }));
        setJobs(jobsWithMockScores);
    }, []);

    // 2. Real-time Listener for User's Training Data (Scores/Notes)
    useEffect(() => {
        if (!db || !isAuthReady || !userId || !currentJob) return;

        const jobDocRef = doc(db, collectionPath, currentJob.id);
        const unsubscribe = onSnapshot(jobDocRef, (docSnap) => {
            if (docSnap.exists()) {
                const data = docSnap.data();
                setCurrentScore(data.score || 5);
                setCurrentNotes(data.notes || "");
                setCurrentLikedPhrases(data.liked_phrases || []);
                setCurrentDislikedPhrases(data.disliked_phrases || []);
            } else {
                // Reset to default if no user data exists for this job
                setCurrentScore(5);
                setCurrentNotes("");
                setCurrentLikedPhrases([]);
                setCurrentDislikedPhrases([]);
            }
            // Update model analysis when job changes
            setModelScore(currentJob.model_score || 0);
            setModelSummary(currentJob.model_summary || "Initial score loaded.");

        }, (error) => console.error("Error fetching job training data:", error));

        return () => unsubscribe();
    }, [db, isAuthReady, userId, currentJob, collectionPath]);


    // --- Core Logic ---

    // Filters the jobs based on the model's initial score
    const filteredJobs = useMemo(() => {
        if (!jobs.length) return [];
        
        // Ensure every job has a model_score for filtering
        const scoredJobs = jobs.filter(j => j.model_score !== undefined);
        
        // Sort by model score descending
        scoredJobs.sort((a, b) => b.model_score - a.model_score);

        // Calculate the cutoff index
        const cutoffIndex = Math.ceil(scoredJobs.length * (filterPercent / 100));
        
        return scoredJobs.slice(0, cutoffIndex);
    }, [jobs, filterPercent]);

    // Resets jobIndex if it falls outside the filtered list
    useEffect(() => {
        if (jobIndex >= filteredJobs.length && filteredJobs.length > 0) {
            setJobIndex(0);
        } else if (filteredJobs.length === 0) {
            setJobIndex(0);
        }
    }, [filteredJobs, jobIndex]);


    // Handles the Gemini API call to populate initial model scores and suggestions
    const handleInitialMatchFilter = useCallback(async () => {
        if (!resumeText || jobs.length === 0) return alert("Please enter your resume text first.");
        if (isProcessing) return;

        setIsProcessing(true);
        // We only score the first 3 for this mock demo, but in real life, you'd 
        // run this Python script/API call on all 3724 jobs and save the result 
        // back to your main job data store.

        const newJobs = await Promise.all(jobs.map(async (job) => {
            const { score, summary, liked_phrases, disliked_phrases } = await calculateSimilarityScore(
                resumeText, job.title, job.description
            );
            
            // Auto-populate the highlights for training review
            if (job.id === currentJob.id) {
                setCurrentLikedPhrases(liked_phrases);
                setCurrentDislikedPhrases(disliked_phrases);
            }

            return { 
                ...job, 
                model_score: score,
                model_summary: summary,
                // These predicted phrases are great starting points for the user annotation
                predicted_liked: liked_phrases,
                predicted_disliked: disliked_phrases
            };
        }));

        setJobs(newJobs);
        setIsProcessing(false);
        setJobIndex(0); // Go back to the first best match
    }, [resumeText, jobs, currentJob]);


    // Saves the user's score, notes, and highlights to Firestore
    const saveTrainingData = useCallback(async () => {
        if (!db || !userId || !currentJob) {
            console.error("Cannot save: Database, user ID, or current job missing.");
            return;
        }
        
        const docRef = doc(db, collectionPath, currentJob.id);
        const trainingData = {
            jobId: currentJob.id,
            score: currentScore,
            notes: currentNotes,
            liked_phrases: currentLikedPhrases,
            disliked_phrases: currentDislikedPhrases,
            timestamp: serverTimestamp(),
            // Include the final model score as context for training
            initial_model_score: modelScore, 
            initial_model_summary: modelSummary
        };

        try {
            await setDoc(docRef, trainingData, { merge: true });
            console.log("Training data saved for job:", currentJob.id);
        } catch (e) {
            console.error("Error adding document: ", e);
        }
    }, [db, userId, currentJob, currentScore, currentNotes, currentLikedPhrases, currentDislikedPhrases, modelScore, modelSummary, collectionPath]);

    // Handles moving to the next job and auto-saving the current one
    const handleNextJob = useCallback(async () => {
        if (!currentJob) return;

        // Save the current annotation before moving on
        await saveTrainingData();

        // Move to the next job in the filtered list
        if (jobIndex < filteredJobs.length - 1) {
            setJobIndex(prev => prev + 1);
        } else {
            // Loop back or show completion message
            setJobIndex(0);
            alert("End of the filtered list reached. Looping back to the first job.");
        }
    }, [jobIndex, filteredJobs.length, currentJob, saveTrainingData]);

    const handlePhraseToggle = (phrase, type) => {
        const setPhraseState = type === 'like' ? setCurrentLikedPhrases : setCurrentDislikedPhrases;
        const currentPhrases = type === 'like' ? currentLikedPhrases : currentDislikedPhrases;
        const otherPhrases = type === 'like' ? currentDislikedPhrases : currentLikedPhrases;
        const setOtherPhraseState = type === 'like' ? setCurrentDislikedPhrases : setCurrentLikedPhrases;

        if (currentPhrases.includes(phrase)) {
            // Remove
            setPhraseState(currentPhrases.filter(p => p !== phrase));
        } else {
            // Add and remove from the other list if present
            setPhraseState([...currentPhrases, phrase]);
            setOtherPhraseState(otherPhrases.filter(p => p !== phrase));
        }
    };

    // --- Utility Components ---

    const LoadingSpinner = () => (
        <div className="flex items-center space-x-2 text-indigo-500">
            <svg className="animate-spin h-5 w-5 mr-3" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            Processing...
        </div>
    );

    const JobDescriptionAnnotator = ({ job, liked, disliked, onToggle }) => {
        if (!job) return null;

        const tokenize = (text) => text.split(/(\s+|[.,?!:;'"()])/).filter(t => t.trim() !== '');

        return (
            <div className="text-gray-700 leading-relaxed max-h-96 overflow-y-auto bg-gray-50 p-4 rounded-lg">
                <p className="text-sm font-semibold mb-2 text-indigo-600">Click words/phrases below to highlight them as liked/disliked training data.</p>
                {tokenize(job.description).map((token, index) => {
                    const isLiked = liked.includes(token);
                    const isDisliked = disliked.includes(token);
                    
                    let classes = "cursor-pointer transition-all duration-150 rounded-sm";
                    if (isLiked) {
                        classes += " bg-emerald-200 text-emerald-800 font-medium shadow-md ring-2 ring-emerald-500";
                    } else if (isDisliked) {
                        classes += " bg-red-200 text-red-800 font-medium shadow-md ring-2 ring-red-500";
                    } else {
                        classes += " hover:bg-yellow-100";
                    }

                    if (token.match(/(\s+|[.,?!:;'"()])/)) {
                        // Keep spaces and punctuation unclickable but preserved in layout
                        return <span key={index}>{token}</span>;
                    }

                    return (
                        <span 
                            key={index} 
                            className={classes}
                            onClick={() => {
                                // Simple logic: if already liked, toggle to disliked. If already disliked, remove. If neither, toggle to liked.
                                if (isLiked) {
                                    onToggle(token, 'dislike'); // Switch from like to dislike
                                } else if (isDisliked) {
                                    onToggle(token, 'remove'); // Simple removal
                                    // We pass 'remove' and handle removal logic in the parent
                                    onToggle(token, 'like'); // A quick way to toggle off both
                                } else {
                                    onToggle(token, 'like');
                                }
                            }}
                        >
                            {token}
                        </span>
                    );
                })}
            </div>
        );
    };


    // --- Main Render ---

    return (
        <div className="min-h-screen bg-gray-50 p-4 md:p-8 font-['Inter']">
            <script src="https://cdn.tailwindcss.com"></script>
            
            <div className="max-w-7xl mx-auto">
                <h1 className="text-4xl font-extrabold text-indigo-700 mb-2">Job Match Training Studio</h1>
                <p className="text-gray-500 mb-8">Annotate and score jobs to train your personalized fit model. User ID: <span className="font-mono text-xs bg-gray-200 p-1 rounded">{userId || "Authenticating..."}</span></p>

                {/* --- 1. Resume Input & Filtering --- */}
                <div className="bg-white p-6 rounded-xl shadow-lg mb-8 border border-indigo-100">
                    <h2 className="text-2xl font-semibold text-indigo-600 mb-4">1. Model Initialization & Filtering</h2>
                    
                    <div className="grid md:grid-cols-3 gap-6">
                        <div className="md:col-span-2">
                            <label htmlFor="resume" className="block text-sm font-medium text-gray-700 mb-1">Paste Your Resume (Text Only)</label>
                            <textarea
                                id="resume"
                                rows="4"
                                className="w-full border border-gray-300 rounded-lg p-3 focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                                placeholder="Paste your relevant work experience, skills, and education here..."
                                value={resumeText}
                                onChange={(e) => setResumeText(e.target.value)}
                            ></textarea>
                            <button
                                onClick={handleInitialMatchFilter}
                                disabled={!resumeText || isProcessing}
                                className="mt-3 w-full md:w-auto inline-flex items-center justify-center px-6 py-2 border border-transparent text-base font-medium rounded-full shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition-colors disabled:bg-indigo-300"
                            >
                                {isProcessing ? <LoadingSpinner /> : "Run Initial Model Match"}
                            </button>
                        </div>
                        
                        <div className="md:col-span-1 bg-indigo-50 p-4 rounded-xl">
                            <h3 className="text-lg font-semibold text-indigo-800 mb-2">Filtering Settings</h3>
                            <p className="text-sm text-indigo-700 mb-4">
                                Jobs Loaded: **{jobs.length}** | 
                                Jobs Filtered (Top {filterPercent}%): **{filteredJobs.length}**
                            </p>
                            
                            <label htmlFor="filter-percent" className="block text-sm font-medium text-indigo-700">
                                Filter Jobs (Display Top {filterPercent}%)
                            </label>
                            <input
                                id="filter-percent"
                                type="range"
                                min="10"
                                max="100"
                                step="5"
                                value={filterPercent}
                                onChange={(e) => setFilterPercent(parseInt(e.target.value))}
                                className="w-full h-2 bg-indigo-200 rounded-lg appearance-none cursor-pointer range-lg mt-2"
                            />
                        </div>
                    </div>
                </div>

                {/* --- 2. Job Display & Annotation --- */}
                
                {filteredJobs.length === 0 ? (
                    <div className="text-center py-20 bg-white rounded-xl shadow-lg border border-gray-200">
                        <p className="text-xl text-gray-500">
                            {jobs.length > 0 ? "Adjust the filter or run the Initial Model Match to see jobs." : "No jobs loaded. Please check data source."}
                        </p>
                    </div>
                ) : (
                    <div className="grid lg:grid-cols-3 gap-8">
                        {/* LEFT COLUMN: Job Card & Annotations */}
                        <div className="lg:col-span-2 space-y-6">
                            <div className="bg-white p-6 rounded-xl shadow-xl border-t-4 border-indigo-600">
                                <span className="text-sm font-semibold text-gray-500 block mb-2">Job {jobIndex + 1} of {filteredJobs.length} (Initial Model Fit: <span className={`font-bold ${modelScore >= 70 ? 'text-green-600' : modelScore >= 40 ? 'text-yellow-600' : 'text-red-600'}`}>{modelScore}%</span>)</span>
                                <h2 className="text-3xl font-bold text-gray-900 mb-2">{currentJob?.title}</h2>
                                <div className="flex flex-wrap gap-2 mb-4">
                                    {currentJob?.skills.map(skill => (
                                        <span key={skill} className="text-xs font-medium bg-indigo-100 text-indigo-800 px-3 py-1 rounded-full">{skill}</span>
                                    ))}
                                </div>
                                <p className="text-sm text-gray-600 italic mb-4 border-l-4 border-indigo-200 pl-3">{modelSummary}</p>

                                {/* Job Description with Highlighting */}
                                <h3 className="text-xl font-semibold text-gray-700 mb-3 mt-5">Job Description</h3>
                                <JobDescriptionAnnotator 
                                    job={currentJob}
                                    liked={currentLikedPhrases}
                                    disliked={currentDislikedPhrases}
                                    onToggle={handlePhraseToggle}
                                />
                            </div>
                            
                            {/* Annotation Summary */}
                            <div className="bg-white p-6 rounded-xl shadow-md border border-gray-200">
                                <h3 className="text-xl font-semibold text-gray-700 mb-3">Training Data Summary</h3>
                                <div className="grid grid-cols-2 gap-4">
                                    <div className="p-3 border rounded-lg bg-emerald-50">
                                        <p className="font-semibold text-emerald-700 mb-2">Phrases I Like (Matches)</p>
                                        <ul className="space-y-1 text-sm text-emerald-900">
                                            {currentLikedPhrases.length > 0 ? currentLikedPhrases.map((p, i) => <li key={i}>&bull; {p}</li>) : <li className="italic text-gray-500">None selected.</li>}
                                        </ul>
                                    </div>
                                    <div className="p-3 border rounded-lg bg-red-50">
                                        <p className="font-semibold text-red-700 mb-2">Phrases I Dislike (Gaps)</p>
                                        <ul className="space-y-1 text-sm text-red-900">
                                            {currentDislikedPhrases.length > 0 ? currentDislikedPhrases.map((p, i) => <li key={i}>&bull; {p}</li>) : <li className="italic text-gray-500">None selected.</li>}
                                        </ul>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* RIGHT COLUMN: Scoring & Controls */}
                        <div className="lg:col-span-1">
                            <div className="sticky top-4 space-y-6">
                                {/* User Score */}
                                <div className="bg-white p-6 rounded-xl shadow-xl border border-indigo-200">
                                    <h3 className="text-2xl font-bold text-indigo-600 mb-4">2. Your Match Score (1-10)</h3>
                                    
                                    <div className="flex items-center justify-between mb-4">
                                        <span className="text-lg font-medium text-gray-700">Score:</span>
                                        <span className="text-4xl font-extrabold text-indigo-700">{currentScore}</span>
                                    </div>

                                    <input
                                        type="range"
                                        min="1"
                                        max="10"
                                        step="1"
                                        value={currentScore}
                                        onChange={(e) => setCurrentScore(parseInt(e.target.value))}
                                        className="w-full h-3 bg-indigo-200 rounded-lg appearance-none cursor-pointer range-xl"
                                    />
                                    <div className="flex justify-between text-xs text-gray-500 mt-1">
                                        <span>1 (Poor Match)</span>
                                        <span>10 (Perfect Match)</span>
                                    </div>
                                </div>

                                {/* Notes */}
                                <div className="bg-white p-6 rounded-xl shadow-md border border-gray-200">
                                    <label htmlFor="notes" className="block text-lg font-semibold text-gray-700 mb-3">Notes / Rationale</label>
                                    <textarea
                                        id="notes"
                                        rows="4"
                                        className="w-full border border-gray-300 rounded-lg p-3 focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                                        placeholder="E.g., 'Perfect technology stack, but location is a dealbreaker.' or 'Requires 5 years experience, I only have 3, so score is 6.'"
                                        value={currentNotes}
                                        onChange={(e) => setCurrentNotes(e.target.value)}
                                    ></textarea>
                                </div>

                                {/* Controls */}
                                <div className="space-y-3">
                                    <button
                                        onClick={saveTrainingData}
                                        className="w-full flex items-center justify-center px-4 py-3 border border-transparent text-base font-medium rounded-xl shadow-sm text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500 transition-colors"
                                    >
                                        <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2" viewBox="0 0 20 20" fill="currentColor">
                                            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                                        </svg>
                                        Save Current Annotation
                                    </button>
                                    <button
                                        onClick={handleNextJob}
                                        className="w-full flex items-center justify-center px-4 py-3 border border-transparent text-base font-medium rounded-xl shadow-sm text-indigo-600 bg-indigo-100 hover:bg-indigo-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition-colors"
                                    >
                                        Next Job (Save & Advance)
                                        <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 ml-2" viewBox="0 0 20 20" fill="currentColor">
                                            <path fillRule="evenodd" d="M10.293 15.707a1 1 0 010-1.414L12.586 12H7a1 1 0 010-2h5.586l-2.293-2.293a1 1 0 111.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clipRule="evenodd" />
                                        </svg>
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default App;
