# USER INTERFACE

Any application is not complete without a user interface which not enables the easy access of the system components and services inside but also makes the experience pleasant for the users using it. In order for the API backend to successfully supply its endpoint functionalities over dedicated network protocols, an efficient and user friendly interface was needed to make it happen. For this, we chose streamlit framework which enables the access to the API backend endpoints for the users. It's interactive and responsive design enables a range of advantages for smoothly interacting with the multi-agent Google Workspace Agent framework over natural language. Some of the features this user interface provides are as follows:

### Chat panel with live SSE streaming

The chat panel integrated on the user interface has live server sent event (SSE) streaming which profoundly adds to its purpose of making the interaction between the user and API friendly. Not only the content rendered is streamed live, but also the status or agent's thoughts are displayed in real-time, thereby taking away the boredom of waiting for the actual content to be delivered.

### Account selector (Work/Personal and context hints)

The user interface enables the users to select the type of account they are associating with the username which adds a sense of customization and flexibility for the user, thereby making their experience more engaging and interactive. Upon associating an account with the username, the users have the option to provide additonal information related to their account which can be the type of account or other contextual information known to the user.

### Abstracted technical complexity

The UI interface makes it easier for the users to interact with the complex agentic architecture and API backend by abstracting away all the technical details beyond the user interface visibility. This makes the experience friendlier and the user can engage with the agentic system for longer times without needing to worry about the technical bottlenecks taken cared at the backend itself. Such functionality adds to the user experience provided by the application.

## Streamlit based UI application

We have provided a robut and user friendly front end application to interact with the Google Workspace Agent and perform various associated tasks with the help of natural language. The UI application is developed using streamlit framework and aligns well with the natural language interaction between the user and the agent.

To interact with the agent via the streamlit app, following steps can be taken:

#### 1. API key enabled user login

The first step is to login to the application and access the backend API service for further tasks. This step requires the username and the API key to successfully log in the application enabling communication with the agentic framework through API endpoints. The user needs to contact the developers of this project for gaining the relevant API key.

#### 2. Associating Google cloud email account

Next step for a new user is to associate the username with the email account present on the google cloud project on google cloud console. This step requires the user to safely keep their google oauth credentials in the .env file so that the UI can use the environment variables to supply the refresh token to API backend endpoint and receive the appropriate google account. For chattting with the agent, an account must be linked with a user/

#### 3. Chat operations

Once an account is successfully associated, the core of the project functionality can be accessed via a chat interface. The user can communicate with the agent and ask to perform different tasks. One can schedule meets, events on calenders, manage contacts, and even get google search results just by the natural language interaction.

#### 4. Dissociating email account

The user has the option to dissociate the email account linked with the username. To do this, they can simply click on the dissociate account button and their account will be dissociated from the username.

#### 5. Chat history

The user can access their chat history and responses provided by the agent in the chat history panel. Every chat history has its own id and user can access the different chat histories based on the ids provided.
